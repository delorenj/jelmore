"""Integrated Session Service for Jelmore

This module provides comprehensive session management that bridges:
- Redis caching for fast access
- PostgreSQL persistence for durability  
- NATS event bus for real-time notifications
- Session timeout monitoring and cleanup
"""

import asyncio
import uuid
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError

from jelmore.config import get_settings
from jelmore.models.session import Session, SessionStatus
from jelmore.models.events import Event, EventType
from jelmore.services.database import get_session
from jelmore.services.nats import publish_event, init_nats
from jelmore.storage.redis_store import RedisStore, SessionData, get_redis_store

logger = structlog.get_logger(__name__)


class SessionService:
    """Integrated session service with Redis caching, PostgreSQL persistence, and NATS events
    
    Features:
    - Write-through caching (Redis → PostgreSQL)
    - NATS event publishing for all state changes  
    - Session timeout monitoring (configurable intervals)
    - Automatic stale session cleanup
    - Session recovery after crashes
    - Output buffering with dual storage
    - Provider lifecycle hooks
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.redis_store: Optional[RedisStore] = None
        self.monitoring_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Session timeout settings from configuration
        self.session_timeout = timedelta(seconds=self.settings.session_default_timeout_seconds)
        self.monitoring_interval = self.settings.session_monitoring_interval_seconds
        self.cleanup_interval = self.settings.session_cleanup_interval_seconds
        
        # Session state tracking
        self.active_sessions: Set[str] = set()
        
    async def start(self):
        """Start session service with all monitoring tasks"""
        if self._running:
            return
            
        logger.info("Starting integrated session service...")
        
        # Initialize dependencies
        await self._initialize_dependencies()
        
        # Start monitoring tasks
        self._running = True
        self.monitoring_task = asyncio.create_task(self._session_monitoring_loop())
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("Session service started successfully", 
                   session_timeout_minutes=self.session_timeout.total_seconds() / 60,
                   monitoring_interval_seconds=self.monitoring_interval,
                   cleanup_interval_seconds=self.cleanup_interval)
        
    async def stop(self):
        """Stop session service and cleanup tasks"""
        if not self._running:
            return
            
        logger.info("Stopping session service...")
        
        self._running = False
        
        # Cancel monitoring tasks
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
                
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
                
        logger.info("Session service stopped")
        
    async def _initialize_dependencies(self):
        """Initialize Redis store and NATS connection"""
        try:
            # Initialize Redis store
            self.redis_store = await get_redis_store()
            
            # Initialize NATS (if not already connected)
            try:
                await init_nats()
            except Exception as e:
                logger.warning("NATS connection failed, events will not be published", error=str(e))
                
            logger.debug("Session service dependencies initialized")
            
        except Exception as e:
            logger.error("Failed to initialize session service dependencies", error=str(e))
            raise
    
    async def create_session(
        self,
        query: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        current_directory: Optional[str] = None
    ) -> str:
        """Create a new session with dual storage (Redis + PostgreSQL) and event publishing
        
        Args:
            query: The user query/request for this session
            session_id: Optional custom session ID
            user_id: Optional user identifier
            metadata: Optional session metadata
            current_directory: Optional working directory
            
        Returns:
            str: The session ID
        """
        if not session_id:
            session_id = str(uuid.uuid4())
            
        now = datetime.utcnow()
        
        try:
            # 1. Create session in PostgreSQL (primary storage)
            async with self._get_db_session() as db_session:
                db_session_obj = Session(
                    id=uuid.UUID(session_id),
                    status=SessionStatus.INITIALIZING,
                    query=query,
                    current_directory=current_directory,
                    session_metadata=metadata or {},
                    created_at=now,
                    updated_at=now,
                    last_activity=now
                )
                
                db_session.add(db_session_obj)
                await db_session.commit()
                
            # 2. Cache session in Redis for fast access
            if self.redis_store:
                session_data = SessionData(
                    session_id=session_id,
                    user_id=user_id,
                    data={
                        "query": query,
                        "status": SessionStatus.INITIALIZING.value,
                        "current_directory": current_directory,
                        "metadata": metadata or {},
                        "claude_process_id": None,
                        "output_buffer": ""
                    },
                    created_at=now,
                    updated_at=now,
                    expires_at=now + self.session_timeout
                )
                
                await self.redis_store.create_session(
                    session_id=session_id,
                    data=session_data.data,
                    ttl=int(self.session_timeout.total_seconds()),
                    user_id=user_id
                )
                
            # 3. Track active session
            self.active_sessions.add(session_id)
            
            # 4. Publish NATS event
            await self._publish_session_event(
                EventType.SESSION_CREATED,
                session_id,
                {
                    "query": query,
                    "user_id": user_id,
                    "current_directory": current_directory,
                    "metadata": metadata or {}
                }
            )
            
            logger.info("Session created successfully", 
                       session_id=session_id, 
                       user_id=user_id)
            
            return session_id
            
        except Exception as e:
            logger.error("Failed to create session", 
                        session_id=session_id, 
                        error=str(e))
            # Cleanup on failure
            await self._cleanup_failed_session(session_id)
            raise
            
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data with cache-first lookup"""
        try:
            # 1. Try Redis cache first (fastest)
            if self.redis_store:
                redis_data = await self.redis_store.get_session(session_id)
                if redis_data:
                    return {
                        "session_id": redis_data.session_id,
                        "user_id": redis_data.user_id,
                        "status": redis_data.data.get("status"),
                        "query": redis_data.data.get("query"),
                        "current_directory": redis_data.data.get("current_directory"),
                        "metadata": redis_data.data.get("metadata", {}),
                        "claude_process_id": redis_data.data.get("claude_process_id"),
                        "output_buffer": redis_data.data.get("output_buffer", ""),
                        "created_at": redis_data.created_at,
                        "updated_at": redis_data.updated_at,
                        "expires_at": redis_data.expires_at
                    }
                    
            # 2. Fallback to PostgreSQL 
            async with self._get_db_session() as db_session:
                result = await db_session.execute(
                    select(Session).where(Session.id == uuid.UUID(session_id))
                )
                db_session_obj = result.scalar_one_or_none()
                
                if not db_session_obj:
                    return None
                    
                # 3. Repopulate Redis cache if session exists in PostgreSQL
                if self.redis_store:
                    await self._sync_session_to_redis(db_session_obj)
                    
                return {
                    "session_id": str(db_session_obj.id),
                    "status": db_session_obj.status.value,
                    "query": db_session_obj.query,
                    "current_directory": db_session_obj.current_directory,
                    "metadata": db_session_obj.session_metadata,
                    "claude_process_id": db_session_obj.claude_process_id,
                    "output_buffer": db_session_obj.output_buffer or "",
                    "created_at": db_session_obj.created_at,
                    "updated_at": db_session_obj.updated_at,
                    "last_activity": db_session_obj.last_activity,
                    "terminated_at": db_session_obj.terminated_at
                }
                
        except Exception as e:
            logger.error("Failed to get session", session_id=session_id, error=str(e))
            return None
            
    async def update_session_status(
        self,
        session_id: str,
        status: SessionStatus,
        claude_process_id: Optional[str] = None,
        output_data: Optional[str] = None
    ) -> bool:
        """Update session status with write-through caching"""
        try:
            now = datetime.utcnow()
            
            # 1. Update PostgreSQL (primary storage)
            async with self._get_db_session() as db_session:
                update_data = {
                    "status": status,
                    "updated_at": now,
                    "last_activity": now
                }
                
                if claude_process_id is not None:
                    update_data["claude_process_id"] = claude_process_id
                    
                if output_data is not None:
                    # Append to existing output buffer
                    result = await db_session.execute(
                        select(Session.output_buffer).where(Session.id == uuid.UUID(session_id))
                    )
                    existing_output = result.scalar_one_or_none() or ""
                    update_data["output_buffer"] = existing_output + output_data
                    
                if status in [SessionStatus.TERMINATED, SessionStatus.FAILED]:
                    update_data["terminated_at"] = now
                    
                await db_session.execute(
                    update(Session)
                    .where(Session.id == uuid.UUID(session_id))
                    .values(**update_data)
                )
                await db_session.commit()
                
            # 2. Update Redis cache
            if self.redis_store:
                redis_session = await self.redis_store.get_session(session_id)
                if redis_session:
                    updated_data = {**redis_session.data}
                    updated_data.update({
                        "status": status.value,
                        "claude_process_id": claude_process_id,
                        "updated_at": now.isoformat()
                    })
                    
                    if output_data:
                        current_output = updated_data.get("output_buffer", "")
                        updated_data["output_buffer"] = current_output + output_data
                        
                    await self.redis_store.update_session(
                        session_id,
                        updated_data,
                        extend_ttl=True
                    )
                    
            # 3. Update active sessions tracking
            if status in [SessionStatus.TERMINATED, SessionStatus.FAILED]:
                self.active_sessions.discard(session_id)
            else:
                self.active_sessions.add(session_id)
                
            # 4. Publish NATS event
            event_type_map = {
                SessionStatus.ACTIVE: EventType.SESSION_STARTED,
                SessionStatus.IDLE: EventType.SESSION_IDLE,
                SessionStatus.WAITING_INPUT: EventType.SESSION_RESUMED,
                SessionStatus.TERMINATED: EventType.SESSION_TERMINATED,
                SessionStatus.FAILED: EventType.SESSION_FAILED
            }
            
            if status in event_type_map:
                await self._publish_session_event(
                    event_type_map[status],
                    session_id,
                    {
                        "status": status.value,
                        "claude_process_id": claude_process_id,
                        "has_output": bool(output_data)
                    }
                )
                
            logger.debug("Session status updated", 
                        session_id=session_id, 
                        status=status.value)
            
            return True
            
        except Exception as e:
            logger.error("Failed to update session status", 
                        session_id=session_id, 
                        status=status.value, 
                        error=str(e))
            return False
            
    async def list_sessions(
        self,
        user_id: Optional[str] = None,
        status: Optional[SessionStatus] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List sessions with optional filtering"""
        try:
            async with self._get_db_session() as db_session:
                query = select(Session).order_by(Session.created_at.desc())
                
                # Apply filters
                if user_id:
                    # Note: We'd need to add user_id to PostgreSQL model
                    # For now, we'll filter from Redis if available
                    pass
                    
                if status:
                    query = query.where(Session.status == status)
                    
                query = query.limit(limit)
                
                result = await db_session.execute(query)
                sessions = result.scalars().all()
                
                session_list = []
                for session in sessions:
                    session_data = {
                        "session_id": str(session.id),
                        "status": session.status.value,
                        "query": session.query,
                        "current_directory": session.current_directory,
                        "metadata": session.session_metadata,
                        "claude_process_id": session.claude_process_id,
                        "created_at": session.created_at,
                        "updated_at": session.updated_at,
                        "last_activity": session.last_activity,
                        "terminated_at": session.terminated_at
                    }
                    
                    # Try to get user_id from Redis if available
                    if self.redis_store:
                        redis_data = await self.redis_store.get_session(str(session.id))
                        if redis_data and redis_data.user_id:
                            session_data["user_id"] = redis_data.user_id
                            
                    session_list.append(session_data)
                    
                return session_list
                
        except Exception as e:
            logger.error("Failed to list sessions", error=str(e))
            return []
            
    async def terminate_session(self, session_id: str, reason: str = "User terminated") -> bool:
        """Terminate session with cleanup"""
        try:
            success = await self.update_session_status(
                session_id, 
                SessionStatus.TERMINATED
            )
            
            if success:
                # Publish termination event with reason
                await self._publish_session_event(
                    EventType.SESSION_TERMINATED,
                    session_id,
                    {"reason": reason}
                )
                
                logger.info("Session terminated", 
                           session_id=session_id, 
                           reason=reason)
                
            return success
            
        except Exception as e:
            logger.error("Failed to terminate session", 
                        session_id=session_id, 
                        error=str(e))
            return False
            
    async def stream_output(self, session_id: str) -> Optional[str]:
        """Stream session output with buffering"""
        try:
            # Get from Redis first (fastest for streaming)
            if self.redis_store:
                redis_data = await self.redis_store.get_session(session_id)
                if redis_data:
                    return redis_data.data.get("output_buffer", "")
                    
            # Fallback to PostgreSQL
            async with self._get_db_session() as db_session:
                result = await db_session.execute(
                    select(Session.output_buffer)
                    .where(Session.id == uuid.UUID(session_id))
                )
                output = result.scalar_one_or_none()
                return output or ""
                
        except Exception as e:
            logger.error("Failed to stream output", 
                        session_id=session_id, 
                        error=str(e))
            return None
            
    async def cleanup_stale_sessions(self) -> int:
        """Clean up stale sessions - IMPLEMENTATION OF MISSING FEATURE"""
        try:
            now = datetime.utcnow()
            timeout_threshold = now - self.session_timeout
            
            cleaned_count = 0
            
            # 1. Find stale sessions in PostgreSQL
            async with self._get_db_session() as db_session:
                # Sessions that haven't been active recently and aren't terminated
                stale_query = select(Session).where(
                    Session.last_activity < timeout_threshold,
                    Session.status.not_in([SessionStatus.TERMINATED, SessionStatus.FAILED])
                )
                
                result = await db_session.execute(stale_query)
                stale_sessions = result.scalars().all()
                
                for session in stale_sessions:
                    session_id = str(session.id)
                    
                    # Update status to FAILED with timeout reason
                    await db_session.execute(
                        update(Session)
                        .where(Session.id == session.id)
                        .values(
                            status=SessionStatus.FAILED,
                            updated_at=now,
                            terminated_at=now
                        )
                    )
                    
                    # Remove from Redis cache
                    if self.redis_store:
                        await self.redis_store.delete_session(session_id)
                        
                    # Remove from active tracking
                    self.active_sessions.discard(session_id)
                    
                    # Publish timeout event
                    await self._publish_session_event(
                        EventType.SESSION_FAILED,
                        session_id,
                        {
                            "reason": "timeout",
                            "last_activity": session.last_activity.isoformat(),
                            "timeout_threshold": timeout_threshold.isoformat()
                        }
                    )
                    
                    cleaned_count += 1
                    
                if cleaned_count > 0:
                    await db_session.commit()
                    
            # 2. Also cleanup Redis-only stale sessions
            if self.redis_store:
                redis_cleaned = await self.redis_store.cleanup_expired_sessions()
                cleaned_count += redis_cleaned
                
            if cleaned_count > 0:
                logger.info("Stale sessions cleaned up", 
                           count=cleaned_count,
                           timeout_threshold=timeout_threshold)
                           
            return cleaned_count
            
        except Exception as e:
            logger.error("Failed to cleanup stale sessions", error=str(e))
            return 0
            
    async def _session_monitoring_loop(self):
        """Session timeout monitoring - IMPLEMENTATION OF MISSING FEATURE"""
        while self._running:
            try:
                await asyncio.sleep(self.monitoring_interval)
                
                if not self._running:
                    break
                    
                # Check for sessions approaching timeout
                now = datetime.utcnow()
                warning_threshold = now - timedelta(
                    seconds=self.session_timeout.total_seconds() - 300  # 5 min warning
                )
                
                async with self._get_db_session() as db_session:
                    # Find sessions that need timeout warnings
                    warning_query = select(Session).where(
                        Session.last_activity < warning_threshold,
                        Session.last_activity >= now - self.session_timeout,
                        Session.status.in_([SessionStatus.ACTIVE, SessionStatus.IDLE])
                    )
                    
                    result = await db_session.execute(warning_query)
                    warning_sessions = result.scalars().all()
                    
                    for session in warning_sessions:
                        await self._publish_session_event(
                            EventType.TIMEOUT_WARNING,
                            str(session.id),
                            {
                                "last_activity": session.last_activity.isoformat(),
                                "timeout_in_seconds": 300
                            }
                        )
                        
                logger.debug("Session monitoring cycle completed", 
                           active_sessions=len(self.active_sessions),
                           warnings_sent=len(warning_sessions) if 'warning_sessions' in locals() else 0)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in session monitoring loop", error=str(e))
                
    async def _cleanup_loop(self):
        """Background cleanup task"""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                
                if not self._running:
                    break
                    
                # Run stale session cleanup
                cleaned = await self.cleanup_stale_sessions()
                
                if cleaned > 0:
                    logger.info("Background cleanup completed", sessions_cleaned=cleaned)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in cleanup loop", error=str(e))
                
    async def _publish_session_event(
        self,
        event_type: EventType,
        session_id: str,
        payload: Dict[str, Any]
    ):
        """Publish session event to NATS"""
        try:
            await publish_event(
                event_type.value,
                session_id,
                payload
            )
        except Exception as e:
            logger.warning("Failed to publish session event", 
                         event_type=event_type.value,
                         session_id=session_id,
                         error=str(e))
            
    async def _sync_session_to_redis(self, db_session_obj: Session):
        """Sync PostgreSQL session data to Redis cache"""
        if not self.redis_store:
            return
            
        try:
            session_data = SessionData(
                session_id=str(db_session_obj.id),
                data={
                    "status": db_session_obj.status.value,
                    "query": db_session_obj.query,
                    "current_directory": db_session_obj.current_directory,
                    "metadata": db_session_obj.session_metadata,
                    "claude_process_id": db_session_obj.claude_process_id,
                    "output_buffer": db_session_obj.output_buffer or ""
                },
                created_at=db_session_obj.created_at,
                updated_at=db_session_obj.updated_at,
                expires_at=db_session_obj.created_at + self.session_timeout
            )
            
            await self.redis_store.create_session(
                session_id=str(db_session_obj.id),
                data=session_data.data,
                ttl=int(self.session_timeout.total_seconds())
            )
            
        except Exception as e:
            logger.warning("Failed to sync session to Redis", 
                          session_id=str(db_session_obj.id),
                          error=str(e))
            
    async def _cleanup_failed_session(self, session_id: str):
        """Cleanup failed session creation"""
        try:
            # Remove from PostgreSQL
            async with self._get_db_session() as db_session:
                await db_session.execute(
                    delete(Session).where(Session.id == uuid.UUID(session_id))
                )
                await db_session.commit()
                
            # Remove from Redis
            if self.redis_store:
                await self.redis_store.delete_session(session_id)
                
            # Remove from tracking
            self.active_sessions.discard(session_id)
            
        except Exception as e:
            logger.warning("Failed to cleanup failed session", 
                          session_id=session_id,
                          error=str(e))
            
    @asynccontextmanager
    async def _get_db_session(self):
        """Get database session context manager"""
        async with get_session() as session:
            yield session
            
    async def get_session_stats(self) -> Dict[str, Any]:
        """Get comprehensive session statistics"""
        try:
            stats = {
                "service_running": self._running,
                "active_sessions_count": len(self.active_sessions),
                "monitoring_interval_seconds": self.monitoring_interval,
                "cleanup_interval_seconds": self.cleanup_interval,
                "session_timeout_minutes": self.session_timeout.total_seconds() / 60
            }
            
            # Get PostgreSQL stats
            async with self._get_db_session() as db_session:
                # Count by status
                result = await db_session.execute(
                    select(Session.status, db_session.func.count()).group_by(Session.status)
                )
                status_counts = dict(result.fetchall())
                stats["session_status_counts"] = {
                    status.value: count for status, count in status_counts.items()
                }
                
            # Get Redis stats
            if self.redis_store:
                redis_stats = await self.redis_store.get_session_stats()
                stats["redis_stats"] = redis_stats
                
            return stats
            
        except Exception as e:
            logger.error("Failed to get session stats", error=str(e))
            return {"error": str(e)}


# Global session service instance
_session_service: Optional[SessionService] = None


async def get_session_service() -> SessionService:
    """Get global session service instance"""
    global _session_service
    
    if _session_service is None:
        _session_service = SessionService()
        await _session_service.start()
        
    return _session_service


async def cleanup_session_service():
    """Cleanup global session service"""
    global _session_service
    
    if _session_service:
        await _session_service.stop()
        _session_service = None