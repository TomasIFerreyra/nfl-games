import logging
from typing import AsyncGenerator, Optional
import redis.asyncio as aioredis
from redis.asyncio import Redis, ConnectionPool
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_pool: Optional[ConnectionPool] = None
_redis_client: Optional[Redis] = None


async def init_redis_pool() -> Optional[Redis]:
    """
    Initializes the global asynchronous Redis connection pool and client.
    Returns the initialized Redis instance, or None if connection fails.
    """
    global _redis_pool, _redis_client
    if _redis_client is not None:
        return _redis_client

    try:
        redis_url = settings.redis_connection_url
        _redis_pool = ConnectionPool.from_url(
            redis_url,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            decode_responses=True,
            socket_timeout=3.0,
            socket_connect_timeout=3.0,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        _redis_client = Redis(connection_pool=_redis_pool)
        # Test ping to verify connectivity
        await _redis_client.ping()
        logger.info(f"Connected to Redis successfully at {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        return _redis_client
    except (RedisError, OSError) as exc:
        logger.warning(
            f"Failed to connect to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}: {exc}. "
            "System will operate in PostgreSQL-fallback mode."
        )
        _redis_client = None
        return None


async def close_redis_pool() -> None:
    """Closes Redis client connections and connection pool upon shutdown."""
    global _redis_pool, _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception as exc:
            logger.warning(f"Error while closing Redis client: {exc}")
        finally:
            _redis_client = None

    if _redis_pool is not None:
        try:
            await _redis_pool.disconnect()
        except Exception as exc:
            logger.warning(f"Error while disconnecting Redis pool: {exc}")
        finally:
            _redis_pool = None


async def get_redis() -> AsyncGenerator[Optional[Redis], None]:
    """
    FastAPI dependency that yields the global Redis client instance.
    Yields None if Redis is unavailable, enabling graceful degradation.
    """
    global _redis_client
    if _redis_client is None:
        # Attempt lazy initialization
        await init_redis_pool()
    yield _redis_client


def get_redis_client_direct() -> Optional[Redis]:
    """Synchronous accessor for the global Redis client reference."""
    return _redis_client
