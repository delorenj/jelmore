"""Claude Code SDK Wrapper - Enhanced Subprocess Management

Manages subprocess interactions with claude-code CLI including:
- Session lifecycle management (start, monitor, keep-alive)
- Output stream capture with JSON parsing
- Session state tracking (active/idle/waiting for input)
- Directory tracking and change detection
- Comprehensive error handling
- NATS event integration
- SessionService integration
"""
import asyncio
import json
import uuid
import subprocess
import shlex
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, AsyncIterator, List
from pathlib import Path
import structlog
from dataclasses import dataclass
from enum import Enum

from jelmore.config import get_settings
from jelmore.models.session import SessionStatus
from jelmore.services.nats import publish_event
from jelmore.services.session_service import get_session_service

settings = get_settings()
logger = structlog.get_logger()


class ClaudeProcessState(str, Enum):
    """Claude process state enum"""
    INITIALIZING = "initializing"
    STARTING = "starting"
    ACTIVE = "active"
    IDLE = "idle"
    WAITING_INPUT = "waiting_input"
    PROCESSING = "processing"
    SUSPENDED = "suspended"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    FAILED = "failed"
    

@dataclass
class ClaudeConfig:
    """Configuration for Claude Code CLI execution"""
    continue_session: bool = False
    max_turns: int = 10
    output_format: str = "stream-json"
    print_mode: bool = True
    timeout_seconds: int = 300
    working_directory: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    additional_args: List[str] = None
    
    def __post_init__(self):
        if self.additional_args is None:
            self.additional_args = []
            
    def to_cli_args(self) -> List[str]:
        """Convert configuration to CLI arguments"""
        args = []
        
        if self.print_mode:
            args.append("--print")
        
        if self.output_format:
            args.extend(["--output-format", self.output_format])
            
        if self.max_turns:
            args.extend(["--max-turns", str(self.max_turns)])
            
        if self.continue_session:
            args.append("--continue")
            
        if self.working_directory:
            args.extend(["--working-directory", self.working_directory])
            
        if self.model:
            args.extend(["--model", self.model])
            
        if self.temperature is not None:
            args.extend(["--temperature", str(self.temperature)])
            
        if self.max_tokens:
            args.extend(["--max-tokens", str(self.max_tokens)])
            
        if self.system_prompt:
            args.extend(["--system", self.system_prompt])
            
        args.extend(self.additional_args)
        
        return args


@dataclass
class SessionMetrics:
    """Session performance metrics"""
    start_time: datetime
    end_time: Optional[datetime] = None
    total_turns: int = 0
    messages_processed: int = 0
    errors_count: int = 0
    directory_changes: int = 0
    file_operations: int = 0
    git_operations: int = 0
    
    @property
    def duration_seconds(self) -> float:
        end = self.end_time or datetime.utcnow()
        return (end - self.start_time).total_seconds()
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "total_turns": self.total_turns,
            "messages_processed": self.messages_processed,
            "errors_count": self.errors_count,
            "directory_changes": self.directory_changes,
            "file_operations": self.file_operations,
            "git_operations": self.git_operations
        }


class ClaudeCodeSession:
    """Enhanced Claude Code session with comprehensive subprocess management"""
    
    def __init__(self, session_id: Optional[str] = None, config: Optional[ClaudeConfig] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.config = config or ClaudeConfig()
        
        # Process management
        self.process: Optional[asyncio.subprocess.Process] = None
        self.process_id: Optional[int] = None
        self.state = ClaudeProcessState.INITIALIZING
        
        # Session tracking
        self.current_directory = str(Path(self.config.working_directory or Path.cwd()).resolve())
        self.initial_directory = self.current_directory
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.last_heartbeat = datetime.utcnow()
        
        # Output management
        self.output_buffer: List[Dict[str, Any]] = []
        self.raw_output_buffer: List[str] = []
        self._output_queue: asyncio.Queue = asyncio.Queue()
        self._error_queue: asyncio.Queue = asyncio.Queue()
        
        # Monitoring tasks
        self._monitor_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._directory_watcher_task: Optional[asyncio.Task] = None
        
        # State tracking
        self.metrics = SessionMetrics(start_time=self.created_at)
        self.environment_snapshot: Dict[str, str] = {}
        self.git_state: Optional[Dict[str, Any]] = None
        
        # Flags
        self._shutdown_requested = False
        self._suspended = False
        
        logger.debug("ClaudeCodeSession initialized", 
                    session_id=self.session_id,
                    working_directory=self.current_directory,
                    config=self.config.__dict__)
    
    async def start(self, query: str) -> str:
        """Start the Claude Code session with enhanced error handling and monitoring"""
        try:
            self.state = ClaudeProcessState.STARTING
            await self._update_session_service()
            
            # Capture environment snapshot
            self._capture_environment_snapshot()
            
            # Build command
            cmd = [settings.claude_code_bin]
            cmd.extend(self.config.to_cli_args())
            cmd.append(query)  # Add query as the final argument
            
            # Prepare environment
            env = os.environ.copy()
            if self.config.working_directory:
                env['PWD'] = self.config.working_directory
            
            logger.info("Starting Claude Code session", 
                       session_id=self.session_id, 
                       command=shlex.join(cmd),
                       working_directory=self.current_directory,
                       config=self.config.__dict__)
            
            # Start the subprocess with comprehensive configuration
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                cwd=self.current_directory,
                env=env,
                start_new_session=True,  # Create new process group
                preexec_fn=None if os.name == 'nt' else os.setsid
            )
            
            self.process_id = self.process.pid
            self.state = ClaudeProcessState.ACTIVE
            self.last_activity = datetime.utcnow()
            
            # Start all monitoring tasks
            await self._start_monitoring_tasks()
            
            # Update session service and publish events
            await self._update_session_service()
            await self._publish_event("session.started", {
                "query": query,
                "process_id": self.process_id,
                "working_directory": self.current_directory,
                "config": self.config.__dict__
            })
            
            logger.info("Claude Code session started successfully", 
                       session_id=self.session_id,
                       process_id=self.process_id)
            
            return self.session_id
            
        except Exception as e:
            self.state = ClaudeProcessState.FAILED
            self.metrics.errors_count += 1
            
            logger.error("Failed to start Claude Code session", 
                        session_id=self.session_id,
                        error=str(e))
            
            await self._update_session_service()
            await self._publish_event("session.failed", {
                "error": str(e),
                "query": query
            })
            
            raise RuntimeError(f"Failed to start Claude Code session: {e}")
    
    async def continue_session(self, input_text: str) -> str:
        """Continue session with user input - implements interface requirement"""
        if self.state != ClaudeProcessState.WAITING_INPUT:
            raise ValueError(f"Session not waiting for input (state: {self.state})")
        
        if not self.process or not self.process.stdin:
            raise RuntimeError("Process not available for input")
        
        try:
            # Send input to the process
            input_data = f"{input_text}\n".encode()
            self.process.stdin.write(input_data)
            await self.process.stdin.drain()
            
            # Update state and activity
            self.state = ClaudeProcessState.ACTIVE
            self.last_activity = datetime.utcnow()
            self.metrics.total_turns += 1
            
            logger.info("Input sent to Claude session", 
                       session_id=self.session_id,
                       input_length=len(input_text))
            
            await self._update_session_service()
            await self._publish_event("session.resumed", {
                "input_length": len(input_text)
            })
            
            return self.session_id
            
        except Exception as e:
            self.state = ClaudeProcessState.FAILED
            self.metrics.errors_count += 1
            
            logger.error("Failed to send input to session", 
                        session_id=self.session_id,
                        error=str(e))
            
            await self._update_session_service()
            await self._publish_event("session.failed", {
                "error": str(e),
                "context": "input_failed"
            })
            
            raise RuntimeError(f"Failed to send input: {e}")
    
    async def read_output(self) -> AsyncIterator[str]:
        """Stream output from session - implements interface requirement"""
        while self.state not in [ClaudeProcessState.TERMINATED, ClaudeProcessState.FAILED]:
            try:
                data = await asyncio.wait_for(
                    self._output_queue.get(),
                    timeout=1.0
                )
                
                # Convert structured data to string for interface compliance
                if isinstance(data, dict):
                    yield json.dumps(data)
                else:
                    yield str(data)
                    
            except asyncio.TimeoutError:
                # Send heartbeat if no activity
                if (datetime.utcnow() - self.last_activity).seconds > 30:
                    yield json.dumps({
                        "type": "heartbeat",
                        "session_id": self.session_id,
                        "state": self.state.value,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                continue
            except Exception as e:
                logger.error("Error in output stream", 
                           session_id=self.session_id,
                           error=str(e))
                yield json.dumps({
                    "type": "error",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                })
                break
    
    async def stream_output(self) -> AsyncIterator[Dict[str, Any]]:
        """Stream structured output from the session"""
        while self.state not in [ClaudeProcessState.TERMINATED, ClaudeProcessState.FAILED]:
            try:
                data = await asyncio.wait_for(
                    self._output_queue.get(), 
                    timeout=1.0
                )
                yield data
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Error in structured output stream", 
                           session_id=self.session_id,
                           error=str(e))
                break
    
    async def stop(self) -> None:
        """Stop the Claude Code session - implements interface requirement"""
        await self.terminate()
    
    async def terminate(self) -> None:
        """Comprehensive session termination with cleanup"""
        if self._shutdown_requested:
            return
            
        self._shutdown_requested = True
        self.state = ClaudeProcessState.TERMINATING
        
        logger.info("Terminating Claude Code session", 
                   session_id=self.session_id,
                   process_id=self.process_id)
        
        try:
            # Cancel all monitoring tasks
            tasks_to_cancel = [
                self._monitor_task,
                self._heartbeat_task,
                self._directory_watcher_task
            ]
            
            for task in tasks_to_cancel:
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            # Terminate the process gracefully
            if self.process:
                try:
                    # Send SIGTERM first
                    self.process.terminate()
                    
                    # Wait for graceful shutdown
                    await asyncio.wait_for(self.process.wait(), timeout=10)
                    
                    logger.debug("Process terminated gracefully", 
                               session_id=self.session_id,
                               return_code=self.process.returncode)
                    
                except asyncio.TimeoutError:
                    # Force kill if graceful termination fails
                    logger.warning("Process did not terminate gracefully, killing", 
                                 session_id=self.session_id)
                    self.process.kill()
                    await self.process.wait()
                    
        except Exception as e:
            logger.error("Error during session termination", 
                        session_id=self.session_id,
                        error=str(e))
        finally:
            # Update final state
            self.state = ClaudeProcessState.TERMINATED
            self.metrics.end_time = datetime.utcnow()
            
            # Final updates
            await self._update_session_service()
            await self._publish_event("session.completed", {
                "metrics": self.metrics.to_dict(),
                "final_directory": self.current_directory
            })
            
            logger.info("Session terminated successfully", 
                       session_id=self.session_id,
                       duration_seconds=self.metrics.duration_seconds,
                       total_turns=self.metrics.total_turns)
    
    def is_alive(self) -> bool:
        """Check if session is alive - implements interface requirement"""
        if not self.process:
            return False
        return self.process.returncode is None and self.state not in [
            ClaudeProcessState.TERMINATED,
            ClaudeProcessState.FAILED
        ]
    
    async def get_status(self) -> Dict[str, Any]:
        """Get comprehensive session status"""
        is_process_alive = self.is_alive()
        
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "process_id": self.process_id,
            "process_alive": is_process_alive,
            "current_directory": self.current_directory,
            "initial_directory": self.initial_directory,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "suspended": self._suspended,
            "output_buffer_size": len(self.output_buffer),
            "raw_output_buffer_size": len(self.raw_output_buffer),
            "config": self.config.__dict__,
            "metrics": self.metrics.to_dict(),
            "git_state": self.git_state
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for API responses (sync version)"""
        return {
            "id": self.session_id,
            "state": self.state.value,
            "status": self.state.value,  # For backward compatibility
            "process_id": self.process_id,
            "current_directory": self.current_directory,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "output_buffer_size": len(self.output_buffer),
            "metrics": self.metrics.to_dict()
        }
    
    # Additional helper methods for comprehensive session management
    
    async def _start_monitoring_tasks(self):
        """Start all monitoring tasks"""
        self._monitor_task = asyncio.create_task(self._monitor_output())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._directory_watcher_task = asyncio.create_task(self._directory_watcher())
        
        logger.debug("All monitoring tasks started", session_id=self.session_id)
    
    async def _monitor_output(self) -> None:
        """Enhanced output monitoring with comprehensive parsing and error handling"""
        if not self.process:
            return
        
        try:
            # Monitor both stdout and stderr concurrently
            stdout_task = asyncio.create_task(self._monitor_stdout())
            stderr_task = asyncio.create_task(self._monitor_stderr())
            
            # Wait for either to complete (or process to exit)
            done, pending = await asyncio.wait(
                [stdout_task, stderr_task], 
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Monitor task error", 
                        session_id=self.session_id,
                        error=str(e))
            self.metrics.errors_count += 1
        finally:
            if self.state not in [ClaudeProcessState.TERMINATED, ClaudeProcessState.SUSPENDED]:
                self.state = ClaudeProcessState.IDLE
                await self._update_session_service()
    
    async def _monitor_stdout(self) -> None:
        """Monitor stdout with JSON parsing"""
        if not self.process or not self.process.stdout:
            return
            
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    # Process ended
                    break
                
                line_str = line.decode().strip()
                if not line_str:
                    continue
                    
                self.raw_output_buffer.append(line_str)
                self.last_activity = datetime.utcnow()
                self.metrics.messages_processed += 1
                
                # Try to parse as JSON first
                try:
                    data = json.loads(line_str)
                    await self._process_json_output(data)
                except json.JSONDecodeError:
                    # Handle as raw text output
                    await self._process_raw_output(line_str)
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Error monitoring stdout", 
                        session_id=self.session_id,
                        error=str(e))
    
    async def _monitor_stderr(self) -> None:
        """Monitor stderr for errors and warnings"""
        if not self.process or not self.process.stderr:
            return
            
        try:
            while True:
                line = await self.process.stderr.readline()
                if not line:
                    break
                    
                error_str = line.decode().strip()
                if error_str:
                    self.metrics.errors_count += 1
                    await self._error_queue.put(error_str)
                    
                    logger.warning("Claude Code stderr output", 
                                 session_id=self.session_id,
                                 error_output=error_str)
                    
                    # Check for critical errors
                    if any(keyword in error_str.lower() for keyword in ['fatal', 'critical', 'authentication failed']):
                        self.state = ClaudeProcessState.FAILED
                        await self._update_session_service()
                        await self._publish_event("session.failed", {
                            "error": error_str,
                            "error_type": "critical"
                        })
                        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Error monitoring stderr", 
                        session_id=self.session_id,
                        error=str(e))
    
    async def _process_json_output(self, data: Dict[str, Any]) -> None:
        """Process JSON output with comprehensive state tracking"""
        self.last_activity = datetime.utcnow()
        
        # Determine state changes from output type
        output_type = data.get("type", "")
        content = data.get("content", "")
        
        if output_type == "system":
            if "waiting" in content.lower() or "input" in content.lower():
                self.state = ClaudeProcessState.WAITING_INPUT
            elif "completed" in content.lower() or "finished" in content.lower():
                self.state = ClaudeProcessState.IDLE
        elif output_type == "assistant":
            self.state = ClaudeProcessState.ACTIVE
        elif output_type == "tool_use":
            self.state = ClaudeProcessState.PROCESSING
            await self._process_tool_use(data)
        elif output_type == "tool_result":
            await self._process_tool_result(data)
            
        # Add to structured output buffer
        self.output_buffer.append({
            **data,
            "timestamp": self.last_activity.isoformat(),
            "session_id": self.session_id
        })
        
        # Maintain buffer size limit
        if len(self.output_buffer) > settings.session_output_buffer_size:
            self.output_buffer.pop(0)
        
        # Queue for streaming
        await self._output_queue.put(data)
        
        # Update session service periodically
        await self._update_session_service()
    
    async def _process_raw_output(self, output: str) -> None:
        """Process non-JSON output"""
        self.last_activity = datetime.utcnow()
        
        # Create structured data for raw output
        data = {
            "type": "raw_output",
            "content": output,
            "timestamp": self.last_activity.isoformat(),
            "session_id": self.session_id
        }
        
        self.output_buffer.append(data)
        if len(self.output_buffer) > settings.session_output_buffer_size:
            self.output_buffer.pop(0)
            
        await self._output_queue.put(data)
    
    async def _process_tool_use(self, data: Dict[str, Any]) -> None:
        """Process tool use events for tracking"""
        tool_name = data.get("name", "")
        tool_input = data.get("input", {})
        
        if tool_name == "bash" or tool_name == "Bash":
            command = tool_input.get("command", "")
            await self._process_bash_command(command)
        elif tool_name in ["Read", "Write", "Edit", "MultiEdit"]:
            self.metrics.file_operations += 1
            file_path = tool_input.get("file_path", tool_input.get("path", ""))
            await self._publish_event("session.file_modified", {
                "tool": tool_name,
                "file_path": file_path,
                "operation": tool_name.lower()
            })
    
    async def _process_tool_result(self, data: Dict[str, Any]) -> None:
        """Process tool results"""
        # Tool completed, return to active state
        self.state = ClaudeProcessState.ACTIVE
        
        # Check for errors in tool results
        content = str(data.get("content", ""))
        if any(error_word in content.lower() for error_word in ['error', 'failed', 'exception']):
            self.metrics.errors_count += 1
            logger.warning("Tool execution error detected", 
                          session_id=self.session_id,
                          tool_result=content[:200])  # Truncate long results
    
    async def _process_bash_command(self, command: str) -> None:
        """Process bash commands for special tracking"""
        if not command:
            return
            
        # Track directory changes
        if command.strip().startswith("cd "):
            await self._handle_directory_change(command)
        
        # Track git operations
        if "git" in command:
            self.metrics.git_operations += 1
            await self._track_git_operation(command)
    
    async def _handle_directory_change(self, command: str) -> None:
        """Handle directory change commands"""
        # Extract new directory from cd command
        parts = command.strip().split()
        if len(parts) < 2:
            return
            
        new_dir = " ".join(parts[1:]).strip('"\'')
        
        # Resolve relative path
        if not new_dir.startswith("/"):
            new_dir = str(Path(self.current_directory) / new_dir)
            
        try:
            resolved_dir = str(Path(new_dir).resolve())
            if resolved_dir != self.current_directory:
                old_directory = self.current_directory
                self.current_directory = resolved_dir
                self.metrics.directory_changes += 1
                
                logger.info("Directory changed", 
                           session_id=self.session_id,
                           old_directory=old_directory,
                           new_directory=self.current_directory)
                
                await self._publish_event("session.directory_changed", {
                    "old_directory": old_directory,
                    "new_directory": self.current_directory,
                    "command": command
                })
                
        except Exception as e:
            logger.warning("Failed to resolve directory change", 
                          session_id=self.session_id,
                          command=command,
                          error=str(e))
    
    async def _track_git_operation(self, command: str) -> None:
        """Track git operations"""
        await self._publish_event("session.git_activity", {
            "command": command,
            "directory": self.current_directory
        })
    
    async def _heartbeat_loop(self):
        """Maintain session heartbeat and detect timeouts"""
        while not self._shutdown_requested:
            try:
                await asyncio.sleep(settings.session_keepalive_interval)
                
                if self._shutdown_requested:
                    break
                    
                # Update heartbeat
                self.last_heartbeat = datetime.utcnow()
                
                # Check for timeout
                if (self.last_heartbeat - self.last_activity).seconds > settings.claude_code_timeout:
                    logger.warning("Session timeout detected", 
                                 session_id=self.session_id,
                                 last_activity=self.last_activity)
                    
                    self.state = ClaudeProcessState.FAILED
                    await self._update_session_service()
                    await self._publish_event("session.timeout_warning", {
                        "last_activity": self.last_activity.isoformat(),
                        "timeout_seconds": settings.claude_code_timeout
                    })
                    break
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in heartbeat loop", 
                           session_id=self.session_id,
                           error=str(e))
    
    async def _directory_watcher(self):
        """Watch for directory changes outside of tracked commands"""
        last_known_dir = self.current_directory
        
        while not self._shutdown_requested:
            try:
                await asyncio.sleep(5)  # Check every 5 seconds
                
                if self._shutdown_requested:
                    break
                
                # Get current working directory of the process
                if self.process and self.process.pid:
                    try:
                        # Read /proc/{pid}/cwd on Linux
                        if os.name != 'nt':
                            proc_cwd = Path(f"/proc/{self.process.pid}/cwd").resolve()
                            current_cwd = str(proc_cwd)
                            
                            if current_cwd != last_known_dir:
                                logger.info("Directory change detected via process monitoring", 
                                          session_id=self.session_id,
                                          old_dir=last_known_dir,
                                          new_dir=current_cwd)
                                
                                self.current_directory = current_cwd
                                last_known_dir = current_cwd
                                self.metrics.directory_changes += 1
                                
                                await self._publish_event("session.directory_changed", {
                                    "old_directory": last_known_dir,
                                    "new_directory": current_cwd,
                                    "detected_via": "process_monitoring"
                                })
                                
                    except (FileNotFoundError, PermissionError, OSError):
                        # Process may have ended or no permission
                        pass
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Error in directory watcher", 
                              session_id=self.session_id,
                              error=str(e))
    
    async def _update_session_service(self):
        """Update the integrated session service with current status"""
        try:
            session_service = await get_session_service()
            
            # Map our state to SessionStatus
            status_mapping = {
                ClaudeProcessState.INITIALIZING: SessionStatus.INITIALIZING,
                ClaudeProcessState.STARTING: SessionStatus.INITIALIZING,
                ClaudeProcessState.ACTIVE: SessionStatus.ACTIVE,
                ClaudeProcessState.IDLE: SessionStatus.IDLE,
                ClaudeProcessState.WAITING_INPUT: SessionStatus.WAITING_INPUT,
                ClaudeProcessState.PROCESSING: SessionStatus.ACTIVE,
                ClaudeProcessState.SUSPENDED: SessionStatus.IDLE,
                ClaudeProcessState.TERMINATING: SessionStatus.TERMINATED,
                ClaudeProcessState.TERMINATED: SessionStatus.TERMINATED,
                ClaudeProcessState.FAILED: SessionStatus.FAILED
            }
            
            session_status = status_mapping.get(self.state, SessionStatus.IDLE)
            
            # Create output data for buffer
            if self.output_buffer:
                latest_output = json.dumps(self.output_buffer[-1])
            else:
                latest_output = None
            
            await session_service.update_session_status(
                session_id=self.session_id,
                status=session_status,
                claude_process_id=str(self.process_id) if self.process_id else None,
                output_data=latest_output
            )
            
        except Exception as e:
            logger.warning("Failed to update session service", 
                          session_id=self.session_id,
                          error=str(e))
    
    async def _publish_event(self, event_type: str, payload: Dict[str, Any]):
        """Publish events to NATS bus"""
        try:
            await publish_event(
                event_type,
                self.session_id,
                {
                    **payload,
                    "process_id": self.process_id,
                    "current_directory": self.current_directory,
                    "state": self.state.value
                }
            )
        except Exception as e:
            logger.warning("Failed to publish event", 
                          session_id=self.session_id,
                          event_type=event_type,
                          error=str(e))
    
    def _capture_environment_snapshot(self):
        """Capture current environment state"""
        self.environment_snapshot = {
            "cwd": os.getcwd(),
            "user": os.environ.get("USER", "unknown"),
            "path": os.environ.get("PATH", ""),
            "home": os.environ.get("HOME", ""),
            "shell": os.environ.get("SHELL", "")
        }
        
        # Capture git state if in a git repository
        try:
            git_dir = Path(self.current_directory) / ".git"
            if git_dir.exists():
                self.git_state = {
                    "is_repo": True,
                    "captured_at": datetime.utcnow().isoformat()
                }
        except:
            self.git_state = {"is_repo": False}


class SessionManager:
    """Enhanced session manager with comprehensive process management"""
    
    def __init__(self):
        self.sessions: Dict[str, ClaudeCodeSession] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def start(self):
        """Start session manager with cleanup monitoring"""
        if self._running:
            return
            
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Session manager started")
    
    async def stop(self):
        """Stop session manager and terminate all sessions"""
        if not self._running:
            return
            
        self._running = False
        
        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Terminate all sessions
        termination_tasks = []
        for session in self.sessions.values():
            termination_tasks.append(session.terminate())
            
        if termination_tasks:
            await asyncio.gather(*termination_tasks, return_exceptions=True)
        
        self.sessions.clear()
        logger.info("Session manager stopped")
    
    async def create_session(self, query: str, config: Optional[ClaudeConfig] = None) -> ClaudeCodeSession:
        """Create and start a new session with enhanced configuration"""
        if len(self.sessions) >= settings.max_concurrent_sessions:
            raise RuntimeError(f"Maximum concurrent sessions reached ({settings.max_concurrent_sessions})")
        
        session = ClaudeCodeSession(config=config or ClaudeConfig())
        
        try:
            await session.start(query)
            self.sessions[session.session_id] = session
            
            logger.info("Created new Claude Code session", 
                       session_id=session.session_id,
                       total_sessions=len(self.sessions))
            
            return session
            
        except Exception as e:
            # Cleanup failed session
            if session.session_id in self.sessions:
                del self.sessions[session.session_id]
            raise
    
    def get_session(self, session_id: str) -> Optional[ClaudeCodeSession]:
        """Get a session by ID"""
        return self.sessions.get(session_id)
    
    async def terminate_session(self, session_id: str) -> bool:
        """Terminate a session"""
        session = self.sessions.get(session_id)
        if session:
            try:
                await session.terminate()
                return True
            finally:
                # Always remove from sessions dict
                self.sessions.pop(session_id, None)
        return False
    
    async def list_sessions(self) -> List[Dict[str, Any]]:
        """List all active sessions with async status updates"""
        session_list = []
        for session in self.sessions.values():
            status = await session.get_status()
            session_list.append(status)
        return session_list
    
    async def get_session_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics for all sessions"""
        total_sessions = len(self.sessions)
        active_sessions = sum(1 for s in self.sessions.values() if s.is_alive())
        
        state_counts = {}
        total_errors = 0
        total_turns = 0
        
        for session in self.sessions.values():
            state_counts[session.state.value] = state_counts.get(session.state.value, 0) + 1
            total_errors += session.metrics.errors_count
            total_turns += session.metrics.total_turns
        
        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "state_distribution": state_counts,
            "total_errors": total_errors,
            "total_turns": total_turns,
            "manager_running": self._running
        }
    
    async def _cleanup_loop(self):
        """Cleanup dead sessions periodically"""
        while self._running:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                if not self._running:
                    break
                    
                dead_sessions = []
                for session_id, session in self.sessions.items():
                    if not session.is_alive():
                        dead_sessions.append(session_id)
                
                for session_id in dead_sessions:
                    logger.info("Cleaning up dead session", session_id=session_id)
                    self.sessions.pop(session_id, None)
                    
                if dead_sessions:
                    logger.info("Cleaned up dead sessions", count=len(dead_sessions))
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in session cleanup loop", error=str(e))


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


# For backwards compatibility
session_manager = None  # Will be initialized via get_session_manager()