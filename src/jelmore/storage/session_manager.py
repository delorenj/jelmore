"""High-level session manager for Jelmore

This module provides a session management layer that coordinates between
Redis storage, application logic, and cleanup processes.
"""

import asyncio
import uuid
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

import structlog
from pydantic import BaseModel

from .redis_store import RedisStore, SessionData, get_redis_store
from jelmore.config import get_settings


logger = structlog.get_logger(__name__)


class SessionManager:
    """High-level session manager with automatic cleanup and monitoring
    
    Features:
    - Session lifecycle management
    - Automatic cleanup of expired sessions
    - Session statistics and monitoring
    - Graceful degradation if Redis is unavailable
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.store: Optional[RedisStore] = None
        self.cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def start(self):
        """Start session manager and background tasks"""
        if self._running:
            return
            
        self.store = await get_redis_store()
        self._running = True
        
        # Start cleanup task
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("Session manager started",
                   cleanup_interval=self.settings.session_cleanup_interval_seconds)
        
    async def stop(self):
        """Stop session manager and cleanup tasks"""
        if not self._running:
            return
            
        self._running = False
        
        # Cancel cleanup task
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
                
        logger.info("Session manager stopped")
        
    async def _cleanup_loop(self):
        """Background task for cleaning up expired sessions"""
        while self._running:
            try:
                await asyncio.sleep(self.settings.session_cleanup_interval_seconds)
                
                if self.store:
                    cleaned = await self.store.cleanup_expired_sessions()
                    if cleaned > 0:
                        logger.info("Background cleanup completed", 
                                   sessions_cleaned=cleaned)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in cleanup loop", error=str(e))
                
    @asynccontextmanager
    async def session_context(self, session_id: Optional[str] = None):
        """Context manager for session lifecycle
        
        Usage:
            async with session_manager.session_context() as session:
                # Use session
                session.data['key'] = 'value'
                await session_manager.save_session(session)
        """
        if not self.store:
            raise RuntimeError("Session manager not started")
            
        # Create or retrieve session
        if session_id:
            session = await self.store.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")
        else:
            session_id = str(uuid.uuid4())
            session = await self.store.create_session(session_id)
            
        try:
            yield session
        finally:
            # Session cleanup happens automatically via Redis TTL
            pass
            
    async def create_session(
        self,
        session_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        ttl: Optional[int] = None,
        user_id: Optional[str] = None,
        tags: Optional[Set[str]] = None
    ) -> SessionData:
        """Create a new session
        
        Args:
            session_id: Optional custom session ID (generated if None)
            data: Initial session data
            ttl: Session TTL in seconds
            user_id: Optional user identifier
            tags: Optional session tags
            
        Returns:
            SessionData: Created session
        """
        if not self.store:
            raise RuntimeError("Session manager not started")
            
        if not session_id:
            session_id = str(uuid.uuid4())
            
        return await self.store.create_session(
            session_id=session_id,
            data=data,
            ttl=ttl,
            user_id=user_id,
            tags=tags
        )
        
    async def get_session(self, session_id: str) -> Optional[SessionData]:
        """Get session by ID"""
        if not self.store:
            raise RuntimeError("Session manager not started")
            
        return await self.store.get_session(session_id)
        
    async def update_session(
        self,
        session_id: str,
        data: Dict[str, Any],
        extend_ttl: bool = True
    ) -> bool:
        """Update session data"""
        if not self.store:
            raise RuntimeError("Session manager not started")
            
        return await self.store.update_session(
            session_id=session_id,
            data=data,
            extend_ttl=extend_ttl
        )
        
    async def delete_session(self, session_id: str) -> bool:
        """Delete session"""
        if not self.store:
            raise RuntimeError("Session manager not started")
            
        return await self.store.delete_session(session_id)
        
    async def extend_session(self, session_id: str, ttl: int) -> bool:
        """Extend session TTL"""
        if not self.store:
            raise RuntimeError("Session manager not started")
            
        return await self.store.extend_session(session_id, ttl)
        
    async def list_sessions(
        self,
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> List[SessionData]:
        """List active sessions"""
        if not self.store:
            raise RuntimeError("Session manager not started")
            
        return await self.store.list_sessions(user_id=user_id, limit=limit)
        
    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive session statistics"""
        if not self.store:
            return {
                "error": "Session manager not started",
                "redis_connected": False
            }
            
        # Get Redis stats
        redis_stats = await self.store.get_session_stats()
        
        # Add manager-specific stats
        stats = {
            **redis_stats,
            "cleanup_task_running": self.cleanup_task is not None and not self.cleanup_task.done(),
            "manager_running": self._running,
            "settings": {
                "max_concurrent_sessions": self.settings.max_concurrent_sessions,
                "default_timeout": self.settings.session_default_timeout_seconds,
                "cleanup_interval": self.settings.session_cleanup_interval_seconds
            }
        }
        
        return stats
        
    async def cleanup_user_sessions(self, user_id: str) -> int:
        """Clean up all sessions for a specific user
        
        Args:
            user_id: User identifier
            
        Returns:
            int: Number of sessions cleaned up
        """
        if not self.store:
            raise RuntimeError("Session manager not started")
            
        try:
            # Get all user sessions
            sessions = await self.store.list_sessions(user_id=user_id)
            
            # Delete each session
            cleaned = 0
            for session in sessions:
                success = await self.store.delete_session(session.session_id)
                if success:
                    cleaned += 1
                    
            logger.info("User sessions cleaned up",
                       user_id=user_id,
                       sessions_cleaned=cleaned)
            
            return cleaned
            
        except Exception as e:
            logger.error("Failed to cleanup user sessions",
                        user_id=user_id,
                        error=str(e))
            return 0
            
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on session manager
        
        Returns:
            Dict with health status and diagnostics
        """
        health = {
            "status": "healthy",
            "manager_running": self._running,
            "cleanup_task_running": False,
            "redis_connected": False,
            "errors": []
        }
        
        try:
            # Check cleanup task
            if self.cleanup_task:
                health["cleanup_task_running"] = not self.cleanup_task.done()
                
            # Check Redis connection
            if self.store:
                stats = await self.store.get_session_stats()
                health["redis_connected"] = stats.get("redis_connected", False)
                
                if not health["redis_connected"]:
                    health["errors"].append("Redis not connected")
                    health["status"] = "degraded"
            else:
                health["errors"].append("Session store not initialized")
                health["status"] = "unhealthy"
                
        except Exception as e:
            health["errors"].append(f"Health check failed: {str(e)}")
            health["status"] = "unhealthy"
            
        return health


# Global session manager instance
_session_manager: Optional[SessionManager] = None


async def get_session_manager() -> SessionManager:
    """Get global session manager instance"""
    global _session_manager
    
    if _session_manager is None:
        _session_manager = SessionManager()
        await _session_manager.start()
        
    return _session_manager


async def cleanup_session_manager():
    """Cleanup global session manager"""
    global _session_manager
    
    if _session_manager:
        await _session_manager.stop()
        _session_manager = None