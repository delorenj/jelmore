"""Redis Client Management"""
import redis.asyncio as redis
from typing import Optional
import structlog

from jelmore.config import get_settings

settings = get_settings()
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


async def get_redis_client() -> redis.Redis:
    """Get Redis client (async version)"""
    if not redis_client:
        raise RuntimeError("Redis not initialized")
    return redis_client


async def get_redis_stats():
    """Get Redis statistics"""
    if not redis_client:
        return {"error": "Redis not initialized"}
    
    try:
        info = await redis_client.info()
        return {
            "connected_clients": info.get("connected_clients", 0),
            "used_memory": info.get("used_memory", 0),
            "used_memory_human": info.get("used_memory_human", "0B"),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
            "total_commands_processed": info.get("total_commands_processed", 0),
            "uptime_in_seconds": info.get("uptime_in_seconds", 0),
            "redis_version": info.get("redis_version", "unknown")
        }
    except Exception as e:
        logger.error("Failed to get Redis stats", error=str(e))
        return {"error": str(e)}