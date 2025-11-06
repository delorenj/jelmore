"""Rate Limiting Middleware for Jelmore API

Provides comprehensive rate limiting with different strategies:
- IP-based limiting
- API key-based limiting  
- Endpoint-specific limits
- Burst protection
- Redis-backed storage for distributed deployment
"""

import time
import asyncio
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import structlog
from redis.asyncio import Redis

from jelmore.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class RateLimitExceeded(HTTPException):
    """Rate limit exceeded exception"""
    
    def __init__(self, limit: int, window_seconds: int, retry_after: int = None):
        self.limit = limit
        self.window_seconds = window_seconds
        self.retry_after = retry_after or window_seconds
        
        detail = f"Rate limit exceeded: {limit} requests per {window_seconds} seconds"
        super().__init__(status_code=429, detail=detail)


class RateLimiter:
    """Redis-backed rate limiter with multiple strategies"""
    
    def __init__(self, redis_client: Optional[Redis] = None):
        self.redis = redis_client
        self.local_cache: Dict[str, Dict[str, Any]] = {}
        self.cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def start(self):
        """Start the rate limiter cleanup task"""
        if self._running:
            return
            
        self._running = True
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Rate limiter started")
        
    async def stop(self):
        """Stop the rate limiter"""
        self._running = False
        
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
                
        logger.info("Rate limiter stopped")
        
    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        identifier: str = "default"
    ) -> Dict[str, Any]:
        """Check if request is within rate limit
        
        Args:
            key: Unique identifier for the rate limit (IP, API key, etc.)
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds
            identifier: Rate limit identifier for logging
            
        Returns:
            Dict with rate limit info: allowed, remaining, reset_time, etc.
        """
        now = time.time()
        window_start = now - window_seconds
        
        try:
            if self.redis:
                # Use Redis for distributed rate limiting
                return await self._check_redis_rate_limit(
                    key, limit, window_seconds, now, window_start, identifier
                )
            else:
                # Use local cache for single-instance deployment
                return await self._check_local_rate_limit(
                    key, limit, window_seconds, now, window_start, identifier
                )
                
        except Exception as e:
            logger.error("Rate limit check failed", 
                        key=key, 
                        identifier=identifier, 
                        error=str(e))
            # Fail open - allow request if rate limiting fails
            return {
                "allowed": True,
                "remaining": limit,
                "reset_time": now + window_seconds,
                "total": limit,
                "window_seconds": window_seconds,
                "error": str(e)
            }
    
    async def _check_redis_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        now: float,
        window_start: float,
        identifier: str
    ) -> Dict[str, Any]:
        """Redis-based rate limiting using sliding window"""
        
        redis_key = f"rate_limit:{identifier}:{key}"
        
        # Use Redis pipeline for atomic operations
        pipe = self.redis.pipeline()
        
        # Remove old entries outside the window
        pipe.zremrangebyscore(redis_key, 0, window_start)
        
        # Count current requests in window
        pipe.zcard(redis_key)
        
        # Add current request timestamp
        request_id = f"{now}:{id(self)}"
        pipe.zadd(redis_key, {request_id: now})
        
        # Set expiry for cleanup
        pipe.expire(redis_key, window_seconds + 1)
        
        results = await pipe.execute()
        current_count = results[1] + 1  # +1 for the current request
        
        allowed = current_count <= limit
        remaining = max(0, limit - current_count)
        reset_time = now + window_seconds
        
        if not allowed:
            # Remove the current request since it's not allowed
            await self.redis.zrem(redis_key, request_id)
            
        result = {
            "allowed": allowed,
            "remaining": remaining,
            "reset_time": reset_time,
            "total": limit,
            "window_seconds": window_seconds,
            "current_count": current_count
        }
        
        logger.debug("Redis rate limit check", 
                    key=key,
                    identifier=identifier,
                    **result)
        
        return result
    
    async def _check_local_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        now: float,
        window_start: float,
        identifier: str
    ) -> Dict[str, Any]:
        """Local memory-based rate limiting"""
        
        cache_key = f"{identifier}:{key}"
        
        if cache_key not in self.local_cache:
            self.local_cache[cache_key] = {
                "requests": [],
                "created_at": now
            }
        
        entry = self.local_cache[cache_key]
        requests = entry["requests"]
        
        # Remove old requests outside the window
        entry["requests"] = [req_time for req_time in requests if req_time > window_start]
        
        current_count = len(entry["requests"]) + 1  # +1 for current request
        allowed = current_count <= limit
        remaining = max(0, limit - current_count)
        reset_time = now + window_seconds
        
        if allowed:
            entry["requests"].append(now)
        
        result = {
            "allowed": allowed,
            "remaining": remaining,
            "reset_time": reset_time,
            "total": limit,
            "window_seconds": window_seconds,
            "current_count": current_count
        }
        
        logger.debug("Local rate limit check",
                    key=key,
                    identifier=identifier,
                    **result)
        
        return result
    
    async def _cleanup_loop(self):
        """Clean up old local cache entries"""
        while self._running:
            try:
                await asyncio.sleep(300)  # Clean up every 5 minutes
                
                if not self._running:
                    break
                    
                now = time.time()
                cutoff = now - 3600  # Remove entries older than 1 hour
                
                keys_to_remove = []
                for key, entry in self.local_cache.items():
                    if entry["created_at"] < cutoff and not entry["requests"]:
                        keys_to_remove.append(key)
                
                for key in keys_to_remove:
                    del self.local_cache[key]
                
                if keys_to_remove:
                    logger.debug("Cleaned up rate limit cache", 
                                removed_entries=len(keys_to_remove))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Rate limit cleanup error", error=str(e))


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting"""
    
    def __init__(self, app, rate_limiter: RateLimiter, rules: Dict[str, Dict[str, Any]] = None):
        super().__init__(app)
        self.rate_limiter = rate_limiter
        self.rules = rules or self._default_rules()
    
    def _default_rules(self) -> Dict[str, Dict[str, Any]]:
        """Default rate limiting rules"""
        return {
            "global": {"limit": 1000, "window_seconds": 3600},  # 1000/hour global
            "auth": {"limit": 10, "window_seconds": 60},        # 10/minute auth endpoints  
            "create": {"limit": 20, "window_seconds": 60},      # 20/minute create operations
            "stream": {"limit": 5, "window_seconds": 60},       # 5/minute streaming
            "websocket": {"limit": 10, "window_seconds": 60}    # 10/minute WebSocket connects
        }
    
    async def dispatch(self, request: Request, call_next: Callable):
        """Process request through rate limiting"""
        
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/metrics"]:
            return await call_next(request)
        
        # Get client identifier (IP or API key)
        client_ip = self._get_client_ip(request)
        api_key = self._get_api_key(request)
        client_id = api_key if api_key else client_ip
        
        # Determine rate limit rule
        rule_name = self._get_rule_for_path(request.url.path, request.method)
        rule = self.rules.get(rule_name, self.rules["global"])
        
        try:
            # Check rate limit
            result = await self.rate_limiter.check_rate_limit(
                key=client_id,
                limit=rule["limit"],
                window_seconds=rule["window_seconds"],
                identifier=rule_name
            )
            
            if not result["allowed"]:
                # Rate limit exceeded
                logger.warning("Rate limit exceeded",
                             client_id=client_id,
                             rule=rule_name,
                             path=request.url.path,
                             current_count=result.get("current_count"))
                
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Rate limit exceeded",
                        "message": f"Too many requests: {rule['limit']} per {rule['window_seconds']} seconds",
                        "limit": rule["limit"],
                        "window_seconds": rule["window_seconds"],
                        "retry_after": int(result["reset_time"] - time.time()),
                        "remaining": result["remaining"]
                    },
                    headers={
                        "X-RateLimit-Limit": str(rule["limit"]),
                        "X-RateLimit-Remaining": str(result["remaining"]),
                        "X-RateLimit-Reset": str(int(result["reset_time"])),
                        "X-RateLimit-Window": str(rule["window_seconds"]),
                        "Retry-After": str(int(result["reset_time"] - time.time()))
                    }
                )
            
            # Process request
            response = await call_next(request)
            
            # Add rate limit headers to successful responses
            response.headers["X-RateLimit-Limit"] = str(rule["limit"])
            response.headers["X-RateLimit-Remaining"] = str(result["remaining"])
            response.headers["X-RateLimit-Reset"] = str(int(result["reset_time"]))
            response.headers["X-RateLimit-Window"] = str(rule["window_seconds"])
            
            return response
            
        except Exception as e:
            logger.error("Rate limiting middleware error", error=str(e))
            # Fail open - allow request to proceed
            return await call_next(request)
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address"""
        # Check for forwarded headers (behind proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct connection
        return request.client.host if request.client else "unknown"
    
    def _get_api_key(self, request: Request) -> Optional[str]:
        """Extract API key from request"""
        # Check Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]  # Remove "Bearer " prefix
        
        # Check API key header
        return request.headers.get("X-API-Key")
    
    def _get_rule_for_path(self, path: str, method: str) -> str:
        """Determine which rate limit rule to apply"""
        
        if "/auth" in path or "/login" in path:
            return "auth"
        elif method == "POST" and "/sessions" in path:
            return "create"
        elif "/stream" in path or "/ws" in path:
            return "stream"
        elif method == "GET" and "/websocket" in path:
            return "websocket"
        else:
            return "global"


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


async def get_rate_limiter(redis_client: Optional[Redis] = None) -> RateLimiter:
    """Get or create rate limiter instance"""
    global _rate_limiter
    
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(redis_client)
        await _rate_limiter.start()
        
    return _rate_limiter


async def cleanup_rate_limiter():
    """Cleanup rate limiter"""
    global _rate_limiter
    
    if _rate_limiter:
        await _rate_limiter.stop()
        _rate_limiter = None