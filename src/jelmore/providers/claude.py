"""
Claude Code Provider Implementation

Wrapper for Claude Code CLI with full provider interface compliance.
Supports subprocess management, streaming, and session lifecycle.
"""

import asyncio
import json
import shlex
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


class ClaudeSession(BaseSession):
    """Claude Code session implementation"""
    
    def __init__(self, session_id: Optional[str] = None, config: Optional[SessionConfig] = None):
        super().__init__(session_id, config)
        self.process: Optional[asyncio.subprocess.Process] = None
        self._output_queue: asyncio.Queue[StreamResponse] = asyncio.Queue()
        self._monitor_task: Optional[asyncio.Task] = None
        self.claude_bin = config.environment.get("claude_bin", "claude") if config else "claude"
        
    async def start(self, query: str, continue_session: bool = False) -> None:
        """Start Claude Code session with query"""
        try:
            cmd = [self.claude_bin]
            
            # Build command arguments
            cmd.extend(["--print", query])
            cmd.extend(["--output-format", "stream-json"])
            cmd.extend(["--max-turns", str(self.config.max_turns)])
            
            if continue_session:
                cmd.extend(["--continue"])
                
            if self.config.working_directory:
                cmd.extend(["--working-directory", str(self.config.working_directory)])
                
            # Add model-specific options
            if self.config.model and self.config.model != "default":
                cmd.extend(["--model", self.config.model])
                
            if self.config.temperature is not None:
                cmd.extend(["--temperature", str(self.config.temperature)])
                
            if self.config.max_tokens:
                cmd.extend(["--max-tokens", str(self.config.max_tokens)])
                
            if self.config.system_prompt:
                cmd.extend(["--system", self.config.system_prompt])
            
            logger.info("Starting Claude Code session", 
                       session_id=self.session_id,
                       command=shlex.join(cmd))
            
            # Start subprocess
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                cwd=self.current_directory,
                env={**dict(Path().iterdir()), **self.config.environment} if self.config else None
            )
            
            self.status = SessionStatus.ACTIVE
            self.update_activity()
            
            # Start monitoring output
            self._monitor_task = asyncio.create_task(self._monitor_output())
            
        except Exception as e:
            logger.error("Failed to start Claude session", session_id=self.session_id, error=str(e))
            self.status = SessionStatus.FAILED
            raise SessionError(f"Failed to start session: {e}", "claude", self.session_id)
    
    async def send_message(self, message: str) -> None:
        """Send a message to Claude (for interactive sessions)"""
        if self.status not in [SessionStatus.ACTIVE, SessionStatus.IDLE]:
            raise SessionError(f"Cannot send message in status {self.status}", "claude", self.session_id)
            
        await self.send_input(message)
    
    async def send_input(self, input_text: str) -> None:
        """Send input when session is waiting"""
        if self.status != SessionStatus.WAITING_INPUT or not self.process or not self.process.stdin:
            raise SessionError(f"Session not waiting for input (status: {self.status})", "claude", self.session_id)
        
        try:
            input_data = f"{input_text}\n".encode()
            self.process.stdin.write(input_data)
            await self.process.stdin.drain()
            
            self.status = SessionStatus.ACTIVE
            self.update_activity()
            
            logger.info("Sent input to Claude session", session_id=self.session_id, input_length=len(input_text))
            
        except Exception as e:
            logger.error("Failed to send input", session_id=self.session_id, error=str(e))
            raise SessionError(f"Failed to send input: {e}", "claude", self.session_id)
    
    async def stream_output(self) -> AsyncIterator[StreamResponse]:
        """Stream output from Claude session"""
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
        """Terminate Claude session"""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
                
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Claude process did not terminate gracefully, killing", session_id=self.session_id)
                self.process.kill()
                await self.process.wait()
        
        self.status = SessionStatus.TERMINATED
        self.update_activity()
        logger.info("Claude session terminated", session_id=self.session_id)
    
    async def suspend(self) -> Dict[str, Any]:
        """Suspend session and return state"""
        # Claude Code doesn't directly support suspension, so we save current state
        state = {
            "session_id": self.session_id,
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
        logger.info("Claude session resumed from suspension", session_id=self.session_id)
    
    async def _monitor_output(self) -> None:
        """Monitor and parse output from Claude Code process"""
        if not self.process or not self.process.stdout:
            return
        
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    break
                
                try:
                    output_str = line.decode().strip()
                    if output_str:
                        data = json.loads(output_str)
                        await self._process_output(data)
                except json.JSONDecodeError:
                    # Handle non-JSON output
                    await self._process_raw_output(output_str)
                except Exception as e:
                    logger.error("Error processing output", session_id=self.session_id, error=str(e))
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Monitor task error", session_id=self.session_id, error=str(e))
        finally:
            if self.status not in [SessionStatus.TERMINATED, SessionStatus.SUSPENDED]:
                self.status = SessionStatus.IDLE
    
    async def _process_output(self, data: Dict[str, Any]) -> None:
        """Process JSON output from Claude Code"""
        self.update_activity()
        
        # Determine event type and handle status changes
        event_type = StreamEventType.ASSISTANT
        content = ""
        
        if data.get("type") == "system":
            event_type = StreamEventType.SYSTEM
            content = data.get("content", "")
            
            if "waiting" in content.lower():
                self.status = SessionStatus.WAITING_INPUT
            elif "error" in content.lower():
                event_type = StreamEventType.ERROR
                
        elif data.get("type") == "assistant":
            event_type = StreamEventType.ASSISTANT
            content = data.get("content", "")
            self.status = SessionStatus.ACTIVE
            
        elif data.get("type") == "tool_use":
            event_type = StreamEventType.TOOL_USE
            content = json.dumps(data.get("input", {}))
            
            # Handle directory changes
            if data.get("name") == "bash":
                command = data.get("input", {}).get("command", "")
                if command.startswith("cd "):
                    new_dir = command[3:].strip()
                    if not new_dir.startswith("/"):
                        new_dir = str(Path(self.current_directory) / new_dir)
                    self.current_directory = str(Path(new_dir).resolve())
                    
                    # Send directory change event
                    await self._output_queue.put(StreamResponse(
                        event_type=StreamEventType.DIRECTORY_CHANGE,
                        content=self.current_directory,
                        metadata={"old_directory": self.current_directory, "new_directory": self.current_directory},
                        session_id=self.session_id
                    ))
                    
        elif data.get("type") == "tool_result":
            event_type = StreamEventType.TOOL_RESULT
            content = str(data.get("content", ""))
            
        else:
            content = str(data)
        
        # Add to output buffer
        self.output_buffer.append(data)
        if len(self.output_buffer) > 1000:  # Limit buffer size
            self.output_buffer.pop(0)
        
        # Queue response for streaming
        response = StreamResponse(
            event_type=event_type,
            content=content,
            metadata=data,
            session_id=self.session_id
        )
        await self._output_queue.put(response)
    
    async def _process_raw_output(self, output: str) -> None:
        """Process non-JSON output"""
        if output:
            response = StreamResponse(
                event_type=StreamEventType.SYSTEM,
                content=output,
                metadata={"raw": True},
                session_id=self.session_id
            )
            await self._output_queue.put(response)


class ClaudeProvider(BaseProvider):
    """Claude Code provider implementation"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("claude", config)
        
        # Configure available models
        self._available_models = [
            ModelInfo(
                name="claude-3-5-sonnet-20241022",
                version="3.5",
                capabilities=["text", "code", "tools", "multimodal"],
                context_length=200000,
                supports_streaming=True,
                supports_tools=True,
                max_tokens=8192
            ),
            ModelInfo(
                name="claude-3-opus-20240229",
                version="3.0",
                capabilities=["text", "code", "tools", "multimodal"],
                context_length=200000,
                supports_streaming=True,
                supports_tools=True,
                max_tokens=4096
            ),
            ModelInfo(
                name="claude-3-haiku-20240307",
                version="3.0",
                capabilities=["text", "code", "tools"],
                context_length=200000,
                supports_streaming=True,
                supports_tools=True,
                max_tokens=4096
            ),
        ]
        
        # Configure capabilities
        self._capabilities = ProviderCapabilities(
            supports_streaming=True,
            supports_continuation=True,
            supports_tools=True,
            supports_file_operations=True,
            supports_multimodal=True,
            supports_code_execution=True,
            max_concurrent_sessions=config.get("max_concurrent_sessions", 10),
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
    ) -> ClaudeSession:
        """Create a new Claude session"""
        if len(self.sessions) >= self.capabilities.max_concurrent_sessions:
            raise ProviderError(f"Maximum concurrent sessions reached ({self.capabilities.max_concurrent_sessions})", "claude")
        
        # Apply default config
        if not config:
            config = SessionConfig(
                model=self.config.get("default_model", "claude-3-5-sonnet-20241022"),
                max_turns=self.config.get("max_turns", 10),
                timeout_seconds=self.config.get("timeout_seconds", 300),
                environment={"claude_bin": self.config.get("claude_bin", "claude")}
            )
        
        # Validate model
        if not self.supports_model(config.model):
            raise ProviderError(f"Model {config.model} not supported", "claude")
        
        session = ClaudeSession(session_id, config)
        await session.start(query)
        
        self.sessions[session.session_id] = session
        
        logger.info("Created Claude session", 
                   session_id=session.session_id,
                   model=config.model)
        
        return session
    
    async def get_session(self, session_id: str) -> Optional[ClaudeSession]:
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
        """Check Claude provider health"""
        try:
            # Test if Claude Code is available
            claude_bin = self.config.get("claude_bin", "claude")
            process = await asyncio.create_subprocess_exec(
                claude_bin, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                version = stdout.decode().strip()
                return {
                    "status": "healthy",
                    "provider": "claude",
                    "version": version,
                    "binary": claude_bin,
                    "sessions": len(self.sessions),
                    "available_models": [m.name for m in self.available_models]
                }
            else:
                return {
                    "status": "unhealthy",
                    "provider": "claude",
                    "error": stderr.decode().strip(),
                    "binary": claude_bin
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "provider": "claude",
                "error": str(e)
            }