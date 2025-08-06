"""
Base Provider Interface

Abstract base classes and interfaces for AI providers in Jelmore.
Defines contracts for session management, streaming, and lifecycle operations.
"""

import asyncio
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional, Union
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger()


class SessionStatus(str, Enum):
    """Session status enumeration"""
    INITIALIZING = "initializing"
    ACTIVE = "active"
    IDLE = "idle" 
    WAITING_INPUT = "waiting_input"
    TERMINATED = "terminated"
    FAILED = "failed"
    SUSPENDED = "suspended"


class StreamEventType(str, Enum):
    """Stream event types"""
    SYSTEM = "system"
    ASSISTANT = "assistant"
    USER = "user"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    STATUS_CHANGE = "status_change"
    DIRECTORY_CHANGE = "directory_change"


@dataclass
class ModelInfo:
    """Information about an AI model"""
    name: str
    version: str
    capabilities: List[str]
    context_length: int
    supports_streaming: bool = True
    supports_tools: bool = True
    max_tokens: Optional[int] = None
    cost_per_token: Optional[float] = None


@dataclass
class ProviderCapabilities:
    """Capabilities of a provider"""
    supports_streaming: bool = True
    supports_continuation: bool = True
    supports_tools: bool = True
    supports_file_operations: bool = True
    supports_multimodal: bool = False
    supports_code_execution: bool = True
    max_concurrent_sessions: int = 10
    session_persistence: bool = True


@dataclass
class StreamResponse:
    """Response from streaming operations"""
    event_type: StreamEventType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    session_id: Optional[str] = None


@dataclass
class SessionConfig:
    """Configuration for a session"""
    model: str
    max_turns: int = 10
    timeout_seconds: int = 300
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    working_directory: Optional[Path] = None
    environment: Dict[str, str] = field(default_factory=dict)


class BaseSession(ABC):
    """Base class for AI provider sessions"""
    
    def __init__(self, session_id: Optional[str] = None, config: Optional[SessionConfig] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.config = config or SessionConfig(model="default")
        self.status = SessionStatus.INITIALIZING
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.current_directory = str(self.config.working_directory or Path.cwd())
        self.output_buffer: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
        
    @abstractmethod
    async def start(self, query: str, continue_session: bool = False) -> None:
        """Start the session with initial query"""
        pass
        
    @abstractmethod
    async def send_message(self, message: str) -> None:
        """Send a message to the session"""
        pass
        
    @abstractmethod
    async def send_input(self, input_text: str) -> None:
        """Send input when session is waiting"""
        pass
        
    @abstractmethod
    async def stream_output(self) -> AsyncIterator[StreamResponse]:
        """Stream output from the session"""
        pass
        
    @abstractmethod
    async def terminate(self) -> None:
        """Terminate the session"""
        pass
        
    @abstractmethod
    async def suspend(self) -> Dict[str, Any]:
        """Suspend session and return state"""
        pass
        
    @abstractmethod
    async def resume(self, state: Dict[str, Any]) -> None:
        """Resume session from state"""
        pass
        
    async def get_status(self) -> Dict[str, Any]:
        """Get current session status"""
        return {
            "id": self.session_id,
            "status": self.status.value,
            "model": self.config.model,
            "current_directory": self.current_directory,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "output_buffer_size": len(self.output_buffer),
            "metadata": self.metadata,
        }
        
    def update_activity(self) -> None:
        """Update last activity timestamp"""
        self.last_activity = datetime.utcnow()


class BaseProvider(ABC):
    """Abstract base class for AI providers"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.sessions: Dict[str, BaseSession] = {}
        self._capabilities: Optional[ProviderCapabilities] = None
        self._available_models: List[ModelInfo] = []
        
    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Get provider capabilities"""
        pass
        
    @property
    @abstractmethod
    def available_models(self) -> List[ModelInfo]:
        """Get available models for this provider"""
        pass
        
    @abstractmethod
    async def create_session(
        self,
        query: str,
        config: Optional[SessionConfig] = None,
        session_id: Optional[str] = None
    ) -> BaseSession:
        """Create a new session"""
        pass
        
    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[BaseSession]:
        """Get existing session by ID"""
        pass
        
    @abstractmethod
    async def terminate_session(self, session_id: str) -> bool:
        """Terminate a session"""
        pass
        
    @abstractmethod
    async def list_sessions(self) -> List[Dict[str, Any]]:
        """List all active sessions"""
        pass
        
    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check provider health"""
        pass
        
    async def cleanup_expired_sessions(self, max_age_seconds: int = 3600) -> int:
        """Clean up expired sessions"""
        now = datetime.utcnow()
        expired_sessions = []
        
        for session_id, session in self.sessions.items():
            age = (now - session.last_activity).total_seconds()
            if age > max_age_seconds and session.status not in [SessionStatus.ACTIVE, SessionStatus.WAITING_INPUT]:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            await self.terminate_session(session_id)
            
        return len(expired_sessions)
        
    def get_model_info(self, model_name: str) -> Optional[ModelInfo]:
        """Get information about a specific model"""
        for model in self.available_models:
            if model.name == model_name:
                return model
        return None
        
    def supports_model(self, model_name: str) -> bool:
        """Check if provider supports a model"""
        return any(model.name == model_name for model in self.available_models)
        
    async def get_metrics(self) -> Dict[str, Any]:
        """Get provider metrics"""
        active_sessions = sum(1 for s in self.sessions.values() if s.status == SessionStatus.ACTIVE)
        idle_sessions = sum(1 for s in self.sessions.values() if s.status == SessionStatus.IDLE)
        waiting_sessions = sum(1 for s in self.sessions.values() if s.status == SessionStatus.WAITING_INPUT)
        
        return {
            "provider": self.name,
            "total_sessions": len(self.sessions),
            "active_sessions": active_sessions,
            "idle_sessions": idle_sessions, 
            "waiting_sessions": waiting_sessions,
            "available_models": [m.name for m in self.available_models],
            "capabilities": {
                "streaming": self.capabilities.supports_streaming,
                "continuation": self.capabilities.supports_continuation,
                "tools": self.capabilities.supports_tools,
                "max_concurrent": self.capabilities.max_concurrent_sessions,
            }
        }


class ProviderError(Exception):
    """Base exception for provider errors"""
    def __init__(self, message: str, provider: str, session_id: Optional[str] = None):
        super().__init__(message)
        self.provider = provider
        self.session_id = session_id


class SessionError(ProviderError):
    """Session-specific errors"""
    pass


class ModelNotSupportedError(ProviderError):
    """Model not supported by provider"""
    pass


class ProviderUnavailableError(ProviderError):
    """Provider is unavailable"""
    pass