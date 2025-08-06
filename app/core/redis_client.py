"""
Redis Client Management
"""
import redis.asyncio as redis
from typing import Optional
import structlog

from app.config import settings

logger = structlog.get_logger()

# Global Redis client
redis_client: Optional[redis.Redis] = None


async def init_redis():
    """Initialize Redis connection"""
    global redis_client
    
    try:
        redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        await redis_client.ping()
        logger.info("Redis connected", url=settings.redis_url)
    except Exception as e:
        logger.error("Failed to connect to Redis", error=str(e))
        raise


async def close_redis():
    """Close Redis connection"""
    global redis_client
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")


def get_redis() -> redis.Redis:
    """Get Redis client"""
    if not redis_client:
        raise RuntimeError("Redis not initialized")
    return redis_client
