from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from typing import AsyncGenerator, Optional
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.redis import close_redis_pool, get_redis, init_redis_pool
from app.db.session import close_db_connection, get_async_session

logger = logging.getLogger(__name__)

# Initialize Sentry error monitoring if configured
if settings.SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            traces_sample_rate=0.2 if settings.ENVIRONMENT == "production" else 1.0,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
            ],
            send_default_pii=False,
        )
        logger.info("Sentry initialized successfully.")
    except Exception as exc:
        logger.warning(f"Could not initialize Sentry: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager handling startup and teardown."""
    # Startup tasks (connections, caches, etc.)
    await init_redis_pool()

    # Automatically ensure daily puzzles for today exist upon startup
    try:
        from app.db.session import async_session_scope
        from app.services.puzzle_pipeline import PuzzlePipelineService
        async with async_session_scope() as session:
            await PuzzlePipelineService.ensure_daily_puzzles(session)
    except Exception as exc:
        logger.warning(f"Startup daily puzzle verification check failed or skipped: {exc}")

    yield
    # Shutdown tasks
    await close_redis_pool()
    await close_db_connection()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="High-performance backend API for NFL Daily Mini-Games Platform",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    redoc_url=f"{settings.API_V1_PREFIX}/redoc",
    lifespan=lifespan,
)

# CORS Middleware with hardened allowed origins
origins = settings.ALLOWED_ORIGINS if isinstance(settings.ALLOWED_ORIGINS, list) else [settings.ALLOWED_ORIGINS]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=settings.ALLOW_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Standardized RFC 7807 Exception Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    error_code = getattr(exc, "error_code", f"HTTP_{exc.status_code}")
    problem_detail = {
        "type": f"https://api.nflminigames.com/v1/errors/{error_code}",
        "title": exc.detail if isinstance(exc.detail, str) else "HTTP Error",
        "status": exc.status_code,
        "detail": str(exc.detail),
        "instance": request.url.path,
        "error_code": error_code,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(status_code=exc.status_code, content=problem_detail)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    invalid_params = [
        {"name": " -> ".join(str(loc) for loc in err.get("loc", [])), "reason": err.get("msg", "Invalid parameter")}
        for err in exc.errors()
    ]
    problem_detail = {
        "type": "https://api.nflminigames.com/v1/errors/UNPROCESSABLE_ENTITY",
        "title": "Validation Error",
        "status": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "detail": "Request payload failed schema validation.",
        "instance": request.url.path,
        "error_code": "VALIDATION_FAILED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "invalid_params": invalid_params,
    }
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=problem_detail)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled internal server error on {request.method} {request.url.path}: {exc}", exc_info=True)
    problem_detail = {
        "type": "https://api.nflminigames.com/v1/errors/INTERNAL_SERVER_ERROR",
        "title": "Internal Server Error",
        "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "detail": "An unexpected server error occurred. Our engineering team has been notified.",
        "instance": request.url.path,
        "error_code": "INTERNAL_SERVER_ERROR",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=problem_detail)


# Health check endpoints for container orchestration (Render, Fly.io, K8s)
@app.get("/health/live", tags=["Health"])
async def liveness_probe() -> dict:
    """Liveness probe: verifies the ASGI process is active and accepting requests."""
    return {
        "status": "live",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
    }


@app.get(
    "/health/ready",
    tags=["Health"],
    responses={
        200: {"description": "All critical backing services are connected."},
        503: {"description": "One or more critical services (PostgreSQL) are unreachable."},
    },
)
@app.get(
    "/health",
    tags=["Health"],
    responses={
        200: {"description": "All critical backing services are connected."},
        503: {"description": "One or more critical services (PostgreSQL) are unreachable."},
    },
)
async def readiness_probe(
    session: AsyncSession = Depends(get_async_session),
    redis_client: Optional[Redis] = Depends(get_redis),
) -> dict:
    """Readiness probe: performs active live checks against PostgreSQL and Redis."""
    checks = {
        "database": "unknown",
        "redis": "unknown",
    }
    is_ready = True

    # 1. PostgreSQL Live Connection Ping
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as exc:
        logger.error(f"Health check failed for PostgreSQL: {exc}")
        checks["database"] = f"unhealthy: {str(exc)}"
        is_ready = False

    # 2. Redis Live Ping (Graceful degradation if Redis is offline)
    if redis_client is not None:
        try:
            await redis_client.ping()
            checks["redis"] = "healthy"
        except Exception as exc:
            logger.warning(f"Health check warning for Redis: {exc}")
            checks["redis"] = f"unhealthy: {str(exc)}"
    else:
        checks["redis"] = "fallback_mode"

    if not is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "checks": checks,
            },
        )

    return {
        "status": "ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "checks": checks,
    }


# Mount API v1 router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)

