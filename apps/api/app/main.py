from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import close_db_connection


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager handling startup and teardown."""
    # Startup tasks (connections, caches, etc.)
    yield
    # Shutdown tasks
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

# CORS Middleware
origins = settings.ALLOWED_ORIGINS if isinstance(settings.ALLOWED_ORIGINS, list) else [settings.ALLOWED_ORIGINS]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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
        "timestamp": datetime.utcnow().isoformat() + "Z",
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
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "invalid_params": invalid_params,
    }
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=problem_detail)


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
    }


# Mount API v1 router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
