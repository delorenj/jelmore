"""
Jelmore Services Integration

Service layer integrating the provider system with FastAPI application.
Handles session management, provider coordination, and API endpoints.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import HTTPException

from .providers import (
    ProviderFactory,
    get_provider_factory, 
    SessionConfig,
    BaseSession,
    create_session_with_auto_selection
)
from .providers.config import load_provider_config, get_provider_config_dict

logger = structlog.get_logger()


class SessionService:
    """Service for managing AI provider sessions"""
    
    def __init__(self, provider_factory: ProviderFactory):
        self.factory = provider_factory
        self._cleanup_task: Optional[asyncio.Task] = None
        
    async def initialize(self, config_path: Optional[str] = None) -> None:
        """Initialize the session service"""
        # Load provider configuration
        config = load_provider_config(config_path)
        config_dict = get_provider_config_dict(config)
        
        # Initialize providers
        from .providers.factory import initialize_providers
        self.factory = await initialize_providers(config_dict)
        
        # Start background cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_sessions())
        
        logger.info("Session service initialized", 
                   providers=self.factory.list_active_providers())
        
    async def shutdown(self) -> None:
        """Shutdown the session service"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
                
        await self.factory.shutdown_all_providers()
        logger.info("Session service shut down")
        
    async def create_session(
        self,
        query: str,
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a new session"""
        try:
            # Build session config
            session_config = SessionConfig(
                model=model or "default",
                max_turns=config.get("max_turns", 10) if config else 10,
                timeout_seconds=config.get("timeout_seconds", 300) if config else 300,
                temperature=config.get("temperature") if config else None,
                max_tokens=config.get("max_tokens") if config else None,
                system_prompt=config.get("system_prompt") if config else None
            )
            
            # Create session with specified provider or auto-selection
            if provider_name:
                provider = await self.factory.get_provider(provider_name)
                if not provider:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Provider '{provider_name}' not found"
                    )
                session = await provider.create_session(query, session_config)
            else:
                # Auto-select provider
                requirements = {}
                if model:
                    requirements["model"] = model
                if config and config.get("capabilities"):
                    requirements["capabilities"] = config["capabilities"]
                if config and config.get("load_balancing", True):
                    requirements["load_balancing"] = True
                if config and config.get("cost_optimization", False):
                    requirements["cost_optimization"] = True
                    
                session = await create_session_with_auto_selection(
                    query=query,
                    requirements=requirements,
                    config=session_config
                )
            
            # Get session status
            session_data = await session.get_status()
            
            logger.info("Session created", 
                       session_id=session.session_id,
                       provider=session_data.get("provider", "unknown"),
                       model=session_data.get("model"))
            
            return session_data
            
        except Exception as e:
            logger.error("Failed to create session", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to create session: {e}")
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session by ID"""
        # Search through all providers
        for provider_name in self.factory.list_active_providers():
            provider = await self.factory.get_provider(provider_name)
            if provider:
                session = await provider.get_session(session_id)
                if session:
                    return await session.get_status()
        return None
    
    async def send_message(self, session_id: str, message: str) -> bool:
        """Send message to session"""
        session = await self._find_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        try:
            await session.send_message(message)
            logger.info("Message sent to session", session_id=session_id)
            return True
        except Exception as e:
            logger.error("Failed to send message", session_id=session_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to send message: {e}")
    
    async def send_input(self, session_id: str, input_text: str) -> bool:
        """Send input to waiting session"""
        session = await self._find_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        try:
            await session.send_input(input_text)
            logger.info("Input sent to session", session_id=session_id)
            return True
        except Exception as e:
            logger.error("Failed to send input", session_id=session_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to send input: {e}")
    
    async def stream_session(self, session_id: str):
        """Stream responses from session"""
        session = await self._find_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        try:
            async for response in session.stream_output():
                yield {
                    "event_type": response.event_type.value,
                    "content": response.content,
                    "metadata": response.metadata,
                    "timestamp": response.timestamp.isoformat(),
                    "session_id": response.session_id
                }
        except Exception as e:
            logger.error("Error streaming session", session_id=session_id, error=str(e))
            yield {
                "event_type": "error",
                "content": f"Stream error: {e}",
                "metadata": {},
                "timestamp": datetime.utcnow().isoformat(),
                "session_id": session_id
            }
    
    async def terminate_session(self, session_id: str) -> bool:
        """Terminate a session"""
        # Find and terminate in the appropriate provider
        for provider_name in self.factory.list_active_providers():
            provider = await self.factory.get_provider(provider_name)
            if provider and await provider.get_session(session_id):
                result = await provider.terminate_session(session_id)
                if result:
                    logger.info("Session terminated", session_id=session_id, provider=provider_name)
                return result
        return False
    
    async def suspend_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Suspend a session and return state"""
        session = await self._find_session(session_id)
        if not session:
            return None
        
        try:
            state = await session.suspend()
            logger.info("Session suspended", session_id=session_id)
            return state
        except Exception as e:
            logger.error("Failed to suspend session", session_id=session_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to suspend session: {e}")
    
    async def resume_session(self, session_id: str, state: Dict[str, Any]) -> bool:
        """Resume a session from state"""
        # Determine provider from state
        provider_name = state.get("provider", self.factory._default_provider)
        if not provider_name:
            raise HTTPException(status_code=400, detail="Cannot determine provider from state")
        
        provider = await self.factory.get_provider(provider_name)
        if not provider:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
        
        try:
            # Create new session and resume
            session = await provider.create_session("", session_id=session_id)
            await session.resume(state)
            logger.info("Session resumed", session_id=session_id, provider=provider_name)
            return True
        except Exception as e:
            logger.error("Failed to resume session", session_id=session_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to resume session: {e}")
    
    async def list_sessions(self, provider_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all sessions, optionally filtered by provider"""
        all_sessions = []
        
        providers_to_check = [provider_name] if provider_name else self.factory.list_active_providers()
        
        for pname in providers_to_check:
            provider = await self.factory.get_provider(pname)
            if provider:
                try:
                    sessions = await provider.list_sessions()
                    # Add provider name to each session
                    for session in sessions:
                        session["provider"] = pname
                    all_sessions.extend(sessions)
                except Exception as e:
                    logger.error("Failed to list sessions for provider", provider=pname, error=str(e))
        
        return all_sessions
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status"""
        try:
            metrics = await self.factory.get_provider_metrics()
            health_results = await self.factory.health_check_all()
            
            return {
                "status": "running",
                "providers": {
                    "total": metrics["total_providers"],
                    "active": len(self.factory.list_active_providers()),
                    "default": metrics["default_provider"],
                    "health": health_results
                },
                "sessions": {
                    "total": sum(
                        provider_metrics.get("total_sessions", 0)
                        for provider_metrics in metrics["providers"].values()
                        if isinstance(provider_metrics, dict)
                    ),
                    "active": sum(
                        provider_metrics.get("active_sessions", 0)
                        for provider_metrics in metrics["providers"].values()
                        if isinstance(provider_metrics, dict)
                    )
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error("Failed to get system status", error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def _find_session(self, session_id: str) -> Optional[BaseSession]:
        """Find a session across all providers"""
        for provider_name in self.factory.list_active_providers():
            provider = await self.factory.get_provider(provider_name)
            if provider:
                session = await provider.get_session(session_id)
                if session:
                    return session
        return None
    
    async def _cleanup_expired_sessions(self) -> None:
        """Background task to clean up expired sessions"""
        while True:
            try:
                total_cleaned = 0
                for provider_name in self.factory.list_active_providers():
                    provider = await self.factory.get_provider(provider_name)
                    if provider:
                        cleaned = await provider.cleanup_expired_sessions(max_age_seconds=3600)
                        total_cleaned += cleaned
                
                if total_cleaned > 0:
                    logger.info("Cleaned up expired sessions", count=total_cleaned)
                
                await asyncio.sleep(60)  # Run every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in cleanup task", error=str(e))
                await asyncio.sleep(60)


# Global service instance
_session_service: Optional[SessionService] = None


async def get_session_service() -> SessionService:
    """Get the global session service instance"""
    global _session_service
    if _session_service is None:
        factory = get_provider_factory()
        _session_service = SessionService(factory)
        await _session_service.initialize()
    return _session_service