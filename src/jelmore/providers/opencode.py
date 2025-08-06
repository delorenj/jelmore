"""
OpenCode Provider Implementation

Implementation for OpenCode AI provider with full interface compliance.
Supports alternative AI models and providers through unified interface.
"""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import structlog

from .base import (
    BaseProvider,
    BaseSession,
    ProviderCapabilities,
    ModelInfo,
    SessionConfig,
    SessionStatus,
    StreamEventType,
    StreamResponse,
    ProviderError,
    SessionError
)

logger = structlog.get_logger()


class OpenCodeSession(BaseSession):
    """OpenCode session implementation"""
    
    def __init__(self, session_id: Optional[str] = None, config: Optional[SessionConfig] = None):
        super().__init__(session_id, config)
        self._output_queue: asyncio.Queue[StreamResponse] = asyncio.Queue()
        self._conversation_history: List[Dict[str, Any]] = []
        self.opencode_bin = config.environment.get("opencode_bin", "opencode") if config else "opencode"
        
    async def start(self, query: str, continue_session: bool = False) -> None:
        """Start OpenCode session with query"""
        try:
            # Initialize conversation history
            if not continue_session:
                self._conversation_history = []
                
            # Add initial system message if configured
            if self.config.system_prompt:
                self._conversation_history.append({
                    "role": "system",
                    "content": self.config.system_prompt
                })
            
            # Add user query
            self._conversation_history.append({
                "role": "user", 
                "content": query
            })
            
            self.status = SessionStatus.ACTIVE
            self.update_activity()
            
            # Process the query
            await self._process_query(query)
            
            logger.info("Started OpenCode session",
                       session_id=self.session_id,
                       model=self.config.model)
            
        except Exception as e:
            logger.error("Failed to start OpenCode session", 
                        session_id=self.session_id, 
                        error=str(e))
            self.status = SessionStatus.FAILED
            raise SessionError(f"Failed to start session: {e}", "opencode", self.session_id)
    
    async def send_message(self, message: str) -> None:
        """Send a message to OpenCode"""
        if self.status not in [SessionStatus.ACTIVE, SessionStatus.IDLE]:
            raise SessionError(f"Cannot send message in status {self.status}", "opencode", self.session_id)
        
        # Add message to conversation history
        self._conversation_history.append({
            "role": "user",
            "content": message
        })
        
        self.status = SessionStatus.ACTIVE
        self.update_activity()
        
        await self._process_query(message)
    
    async def send_input(self, input_text: str) -> None:
        """Send input when session is waiting"""
        if self.status != SessionStatus.WAITING_INPUT:
            raise SessionError(f"Session not waiting for input (status: {self.status})", "opencode", self.session_id)
        
        await self.send_message(input_text)
    
    async def stream_output(self) -> AsyncIterator[StreamResponse]:
        """Stream output from OpenCode session"""
        while self.status not in [SessionStatus.TERMINATED, SessionStatus.FAILED]:
            try:
                response = await asyncio.wait_for(
                    self._output_queue.get(),
                    timeout=1.0
                )
                yield response
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Error in stream output", session_id=self.session_id, error=str(e))
                yield StreamResponse(
                    event_type=StreamEventType.ERROR,
                    content=f"Stream error: {e}",
                    session_id=self.session_id
                )
                break
    
    async def terminate(self) -> None:
        """Terminate OpenCode session"""
        self.status = SessionStatus.TERMINATED
        self.update_activity()
        
        # Clear conversation history to free memory
        self._conversation_history.clear()
        
        logger.info("OpenCode session terminated", session_id=self.session_id)
    
    async def suspend(self) -> Dict[str, Any]:
        """Suspend session and return state"""
        state = {
            "session_id": self.session_id,
            "conversation_history": self._conversation_history.copy(),
            "current_directory": self.current_directory,
            "output_buffer": self.output_buffer.copy(),
            "metadata": self.metadata.copy(),
            "config": {
                "model": self.config.model,
                "max_turns": self.config.max_turns,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "system_prompt": self.config.system_prompt,
                "working_directory": str(self.config.working_directory) if self.config.working_directory else None,
                "environment": self.config.environment,
            },
            "suspended_at": self.last_activity.isoformat(),
        }
        
        self.status = SessionStatus.SUSPENDED
        return state
    
    async def resume(self, state: Dict[str, Any]) -> None:
        """Resume session from state"""
        # Restore session state
        self._conversation_history = state.get("conversation_history", [])
        self.current_directory = state.get("current_directory", str(Path.cwd()))
        self.output_buffer = state.get("output_buffer", [])
        self.metadata = state.get("metadata", {})
        
        # Restore config
        config_data = state.get("config", {})
        self.config = SessionConfig(
            model=config_data.get("model", "default"),
            max_turns=config_data.get("max_turns", 10),
            temperature=config_data.get("temperature"),
            max_tokens=config_data.get("max_tokens"),
            system_prompt=config_data.get("system_prompt"),
            working_directory=Path(config_data["working_directory"]) if config_data.get("working_directory") else None,
            environment=config_data.get("environment", {}),
        )
        
        self.status = SessionStatus.IDLE
        logger.info("OpenCode session resumed from suspension", session_id=self.session_id)
    
    async def _process_query(self, query: str) -> None:
        """Process a query using OpenCode"""
        try:
            # Simulate OpenCode processing
            # In real implementation, this would call the OpenCode API or binary
            
            # Send processing started event
            await self._output_queue.put(StreamResponse(
                event_type=StreamEventType.SYSTEM,
                content="Processing query with OpenCode...",
                session_id=self.session_id
            ))
            
            # Simulate some processing time
            await asyncio.sleep(0.5)
            
            # Generate response based on model capabilities
            if self.config.model in ["deepseek-v3", "kimi-k2"]:
                response_content = await self._generate_advanced_response(query)
            else:
                response_content = await self._generate_basic_response(query)
            
            # Add assistant response to history
            self._conversation_history.append({
                "role": "assistant",
                "content": response_content
            })
            
            # Send response
            await self._output_queue.put(StreamResponse(
                event_type=StreamEventType.ASSISTANT,
                content=response_content,
                metadata={"model": self.config.model, "query": query},
                session_id=self.session_id
            ))
            
            # Add to output buffer
            self.output_buffer.append({
                "type": "assistant",
                "content": response_content,
                "model": self.config.model,
                "timestamp": self.last_activity.isoformat()
            })
            
            if len(self.output_buffer) > 1000:
                self.output_buffer.pop(0)
                
            self.status = SessionStatus.IDLE
            
        except Exception as e:
            logger.error("Error processing query", session_id=self.session_id, error=str(e))
            await self._output_queue.put(StreamResponse(
                event_type=StreamEventType.ERROR,
                content=f"Error processing query: {e}",
                session_id=self.session_id
            ))
            self.status = SessionStatus.FAILED
    
    async def _generate_advanced_response(self, query: str) -> str:
        """Generate response for advanced models"""
        # Simulate advanced model capabilities
        model_responses = {
            "deepseek-v3": f"DeepSeek V3 analysis: {query}\n\nThis is a comprehensive response with deep reasoning capabilities.",
            "kimi-k2": f"Kimi K2 response: {query}\n\nProcessed with advanced multimodal understanding."
        }
        return model_responses.get(self.config.model, f"Advanced response to: {query}")
    
    async def _generate_basic_response(self, query: str) -> str:
        """Generate response for basic models"""
        return f"OpenCode response to: {query}\n\nThis is a basic response from the {self.config.model} model."


class OpenCodeProvider(BaseProvider):
    """OpenCode provider implementation"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("opencode", config)
        
        # Configure available models
        self._available_models = [
            ModelInfo(
                name="deepseek-v3",
                version="3.0",
                capabilities=["text", "code", "reasoning", "multimodal"],
                context_length=128000,
                supports_streaming=True,
                supports_tools=False,
                max_tokens=4096,
                cost_per_token=0.0001
            ),
            ModelInfo(
                name="kimi-k2",
                version="2.0",
                capabilities=["text", "code", "multimodal", "long_context"],
                context_length=2000000,
                supports_streaming=True,
                supports_tools=False,
                max_tokens=4096,
                cost_per_token=0.0002
            ),
            ModelInfo(
                name="qwen2.5-coder",
                version="2.5",
                capabilities=["text", "code"],
                context_length=32000,
                supports_streaming=True,
                supports_tools=False,
                max_tokens=2048,
                cost_per_token=0.00005
            ),
        ]
        
        # Configure capabilities
        self._capabilities = ProviderCapabilities(
            supports_streaming=True,
            supports_continuation=True,
            supports_tools=False,  # OpenCode doesn't support tools yet
            supports_file_operations=False,
            supports_multimodal=True,
            supports_code_execution=False,
            max_concurrent_sessions=config.get("max_concurrent_sessions", 20),
            session_persistence=True
        )
    
    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities
    
    @property
    def available_models(self) -> List[ModelInfo]:
        return self._available_models.copy()
    
    async def create_session(
        self,
        query: str,
        config: Optional[SessionConfig] = None,
        session_id: Optional[str] = None
    ) -> OpenCodeSession:
        """Create a new OpenCode session"""
        if len(self.sessions) >= self.capabilities.max_concurrent_sessions:
            raise ProviderError(f"Maximum concurrent sessions reached ({self.capabilities.max_concurrent_sessions})", "opencode")
        
        # Apply default config
        if not config:
            config = SessionConfig(
                model=self.config.get("default_model", "deepseek-v3"),
                max_turns=self.config.get("max_turns", 10),
                timeout_seconds=self.config.get("timeout_seconds", 180),
                temperature=self.config.get("temperature", 0.7),
                environment={"opencode_bin": self.config.get("opencode_bin", "opencode")}
            )
        
        # Validate model
        if not self.supports_model(config.model):
            raise ProviderError(f"Model {config.model} not supported", "opencode")
        
        session = OpenCodeSession(session_id, config)
        await session.start(query)
        
        self.sessions[session.session_id] = session
        
        logger.info("Created OpenCode session",
                   session_id=session.session_id,
                   model=config.model)
        
        return session
    
    async def get_session(self, session_id: str) -> Optional[OpenCodeSession]:
        """Get existing session by ID"""
        return self.sessions.get(session_id)
    
    async def terminate_session(self, session_id: str) -> bool:
        """Terminate a session"""
        session = self.sessions.get(session_id)
        if session:
            await session.terminate()
            del self.sessions[session_id]
            return True
        return False
    
    async def list_sessions(self) -> List[Dict[str, Any]]:
        """List all active sessions"""
        return [await session.get_status() for session in self.sessions.values()]
    
    async def health_check(self) -> Dict[str, Any]:
        """Check OpenCode provider health"""
        try:
            # Simulate health check
            # In real implementation, this would test the OpenCode service/API
            
            return {
                "status": "healthy",
                "provider": "opencode",
                "version": "1.0.0",
                "binary": self.config.get("opencode_bin", "opencode"),
                "sessions": len(self.sessions),
                "available_models": [m.name for m in self.available_models],
                "api_endpoint": self.config.get("api_endpoint", "http://localhost:8080"),
                "capabilities": {
                    "multimodal": self.capabilities.supports_multimodal,
                    "streaming": self.capabilities.supports_streaming,
                    "max_context": max(m.context_length for m in self.available_models)
                }
            }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "provider": "opencode",
                "error": str(e)
            }