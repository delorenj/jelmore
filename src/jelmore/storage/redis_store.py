"""Redis-backed session store implementation for Jelmore

This module provides a high-performance Redis session store with:
- JSON serialization/deserialization
- TTL and automatic cleanup
- Connection pooling and error handling
- Backward compatibility with existing session formats
"""

import json
import asyncio
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timedelta

import redis.asyncio as aioredis
import structlog
from pydantic import BaseModel, Field

from jelmore.config import get_settings


logger = structlog.get_logger(__name__)


class SessionData(BaseModel):
    """Session data model with metadata"""
    
    session_id: str
    user_id: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    tags: Set[str] = Field(default_factory=set)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            set: lambda v: list(v)
        }


class RedisStore:
    """Redis-backed session store with connection pooling and error handling
    
    Features:
    - Automatic serialization/deserialization
    - TTL management with configurable defaults
    - Connection pooling for high performance
    - Error handling and circuit breaker pattern
    - Backward compatibility with existing sessions
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.redis_pool: Optional[aioredis.ConnectionPool] = None
        self.redis: Optional[aioredis.Redis] = None
        self._connected = False
        self.session_prefix = "jelmore:session:"
        self.default_ttl = self.settings.session_default_timeout_seconds
        
    async def connect(self):
        """Initialize Redis connection pool"""
        if self._connected:
            return
            
        try:
            # Create connection pool
            self.redis_pool = aioredis.ConnectionPool.from_url(
                str(self.settings.redis_url),
                max_connections=self.settings.redis_max_connections,
                retry_on_timeout=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                health_check_interval=30
            )
            
            self.redis = aioredis.Redis(connection_pool=self.redis_pool)
            
            # Test connection
            await self.redis.ping()
            self._connected = True
            
            logger.info("Redis store connected successfully", 
                       pool_size=self.settings.redis_max_connections)
                       
        except Exception as e:
            logger.error("Failed to connect to Redis", error=str(e))
            raise
    
    async def disconnect(self):
        """Close Redis connection pool"""
        if self.redis:
            await self.redis.close()
        if self.redis_pool:
            await self.redis_pool.disconnect()
        self._connected = False
        logger.info("Redis store disconnected")
    
    def _get_key(self, session_id: str) -> str:
        """Get Redis key for session ID"""
        return f"{self.session_prefix}{session_id}"
    
    async def create_session(
        self, 
        session_id: str, 
        data: Optional[Dict[str, Any]] = None,
        ttl: Optional[int] = None,
        user_id: Optional[str] = None,
        tags: Optional[Set[str]] = None
    ) -> SessionData:
        """Create a new session with optional TTL
        
        Args:
            session_id: Unique session identifier
            data: Initial session data
            ttl: Session TTL in seconds (defaults to configured value)
            user_id: Optional user identifier
            tags: Optional session tags for organization
            
        Returns:
            SessionData: Created session data
            
        Raises:
            RuntimeError: If Redis connection is not established
            redis.RedisError: If Redis operation fails
        """
        if not self._connected:
            await self.connect()
            
        session_data = SessionData(
            session_id=session_id,
            user_id=user_id,
            data=data or {},
            tags=tags or set()
        )
        
        # Set expiration if TTL provided
        if ttl:
            session_data.expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        
        try:
            key = self._get_key(session_id)
            serialized_data = json.dumps(session_data.model_dump(), default=str)
            
            # Set with TTL
            effective_ttl = ttl or self.default_ttl
            await self.redis.setex(key, effective_ttl, serialized_data)
            
            logger.info("Session created", 
                       session_id=session_id, 
                       ttl=effective_ttl,
                       user_id=user_id)
            
            return session_data
            
        except Exception as e:
            logger.error("Failed to create session", 
                        session_id=session_id, 
                        error=str(e))
            raise
    
    async def get_session(self, session_id: str) -> Optional[SessionData]:
        """Retrieve session data by ID
        
        Args:
            session_id: Session identifier
            
        Returns:
            SessionData or None if not found
        """
        if not self._connected:
            await self.connect()
            
        try:
            key = self._get_key(session_id)
            data = await self.redis.get(key)
            
            if not data:
                return None
                
            # Deserialize and validate
            session_dict = json.loads(data)
            
            # Handle backward compatibility - convert old formats
            if 'created_at' not in session_dict:
                session_dict['created_at'] = datetime.utcnow().isoformat()
            if 'updated_at' not in session_dict:
                session_dict['updated_at'] = datetime.utcnow().isoformat()
                
            return SessionData(**session_dict)
            
        except json.JSONDecodeError as e:
            logger.warning("Invalid session data format", 
                          session_id=session_id, 
                          error=str(e))
            # Clean up corrupted session
            await self.delete_session(session_id)
            return None
            
        except Exception as e:
            logger.error("Failed to retrieve session", 
                        session_id=session_id, 
                        error=str(e))
            return None
    
    async def update_session(
        self, 
        session_id: str, 
        data: Dict[str, Any],
        extend_ttl: bool = True
    ) -> bool:
        """Update session data
        
        Args:
            session_id: Session identifier
            data: New session data (replaces existing)
            extend_ttl: Whether to reset TTL to default
            
        Returns:
            bool: Success status
        """
        if not self._connected:
            await self.connect()
            
        try:
            # Get existing session to preserve metadata
            existing = await self.get_session(session_id)
            if not existing:
                logger.warning("Attempted to update non-existent session", 
                              session_id=session_id)
                return False
            
            # Update session data
            existing.data = data
            existing.updated_at = datetime.utcnow()
            
            key = self._get_key(session_id)
            serialized_data = json.dumps(existing.model_dump(), default=str)
            
            if extend_ttl:
                # Reset TTL
                await self.redis.setex(key, self.default_ttl, serialized_data)
            else:
                # Keep existing TTL
                await self.redis.set(key, serialized_data, keepttl=True)
            
            logger.debug("Session updated", 
                        session_id=session_id, 
                        extend_ttl=extend_ttl)
            
            return True
            
        except Exception as e:
            logger.error("Failed to update session", 
                        session_id=session_id, 
                        error=str(e))
            return False
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete session by ID
        
        Args:
            session_id: Session identifier
            
        Returns:
            bool: True if session was deleted, False if not found
        """
        if not self._connected:
            await self.connect()
            
        try:
            key = self._get_key(session_id)
            result = await self.redis.delete(key)
            
            logger.info("Session deleted", 
                       session_id=session_id, 
                       existed=bool(result))
            
            return bool(result)
            
        except Exception as e:
            logger.error("Failed to delete session", 
                        session_id=session_id, 
                        error=str(e))
            return False
    
    async def extend_session(self, session_id: str, ttl: int) -> bool:
        """Extend session TTL
        
        Args:
            session_id: Session identifier
            ttl: New TTL in seconds
            
        Returns:
            bool: Success status
        """
        if not self._connected:
            await self.connect()
            
        try:
            key = self._get_key(session_id)
            result = await self.redis.expire(key, ttl)
            
            if result:
                logger.debug("Session TTL extended", 
                           session_id=session_id, 
                           ttl=ttl)
            else:
                logger.warning("Failed to extend non-existent session", 
                              session_id=session_id)
                
            return bool(result)
            
        except Exception as e:
            logger.error("Failed to extend session TTL", 
                        session_id=session_id, 
                        error=str(e))
            return False
    
    async def list_sessions(
        self, 
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> List[SessionData]:
        """List active sessions with optional filtering
        
        Args:
            user_id: Filter by user ID
            limit: Maximum sessions to return
            
        Returns:
            List[SessionData]: Active sessions
        """
        if not self._connected:
            await self.connect()
            
        try:
            # Get all session keys
            pattern = f"{self.session_prefix}*"
            keys = await self.redis.keys(pattern)
            
            sessions = []
            
            # Process in batches to avoid blocking
            batch_size = 50
            for i in range(0, len(keys), batch_size):
                batch_keys = keys[i:i + batch_size]
                
                # Get all session data in batch
                if batch_keys:
                    values = await self.redis.mget(batch_keys)
                    
                    for key, value in zip(batch_keys, values):
                        if not value:
                            continue
                            
                        try:
                            session_dict = json.loads(value)
                            session = SessionData(**session_dict)
                            
                            # Apply user filter
                            if user_id and session.user_id != user_id:
                                continue
                                
                            sessions.append(session)
                            
                            if len(sessions) >= limit:
                                break
                                
                        except (json.JSONDecodeError, ValueError) as e:
                            # Clean up corrupted session
                            session_id = key.decode().replace(self.session_prefix, "")
                            logger.warning("Removing corrupted session", 
                                         session_id=session_id)
                            await self.redis.delete(key)
                            
                if len(sessions) >= limit:
                    break
                    
            logger.debug("Sessions listed", 
                        count=len(sessions), 
                        user_id=user_id)
            
            return sessions[:limit]
            
        except Exception as e:
            logger.error("Failed to list sessions", error=str(e))
            return []
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions (Redis handles TTL automatically)
        
        This method is for additional cleanup logic if needed.
        Redis automatically removes expired keys, but we can use this
        for application-level cleanup tasks.
        
        Returns:
            int: Number of sessions processed
        """
        if not self._connected:
            await self.connect()
            
        try:
            # Get all session keys
            pattern = f"{self.session_prefix}*"
            keys = await self.redis.keys(pattern)
            
            cleaned = 0
            
            for key in keys:
                # Check if key still exists (Redis may have expired it)
                exists = await self.redis.exists(key)
                if not exists:
                    cleaned += 1
                    continue
                    
                # Check application-level expiration
                try:
                    data = await self.redis.get(key)
                    if data:
                        session_dict = json.loads(data)
                        session = SessionData(**session_dict)
                        
                        if (session.expires_at and 
                            session.expires_at < datetime.utcnow()):
                            await self.redis.delete(key)
                            cleaned += 1
                            
                except (json.JSONDecodeError, ValueError):
                    # Remove corrupted data
                    await self.redis.delete(key)
                    cleaned += 1
            
            if cleaned > 0:
                logger.info("Expired sessions cleaned up", count=cleaned)
                
            return cleaned
            
        except Exception as e:
            logger.error("Failed to cleanup expired sessions", error=str(e))
            return 0
    
    async def get_session_stats(self) -> Dict[str, int]:
        """Get session statistics
        
        Returns:
            Dict with session counts and metrics
        """
        if not self._connected:
            await self.connect()
            
        try:
            # Count total sessions
            pattern = f"{self.session_prefix}*"
            keys = await self.redis.keys(pattern)
            total_sessions = len(keys)
            
            # Get Redis memory usage
            memory_info = await self.redis.info("memory")
            used_memory = memory_info.get("used_memory", 0)
            
            return {
                "total_sessions": total_sessions,
                "memory_usage_bytes": used_memory,
                "redis_connected": self._connected
            }
            
        except Exception as e:
            logger.error("Failed to get session stats", error=str(e))
            return {
                "total_sessions": 0,
                "memory_usage_bytes": 0,
                "redis_connected": False
            }


# Global Redis store instance
_redis_store: Optional[RedisStore] = None


async def get_redis_store() -> RedisStore:
    """Get global Redis store instance"""
    global _redis_store
    
    if _redis_store is None:
        _redis_store = RedisStore()
        await _redis_store.connect()
        
    return _redis_store


async def cleanup_redis_store():
    """Cleanup global Redis store"""
    global _redis_store
    
    if _redis_store:
        await _redis_store.disconnect()
        _redis_store = None