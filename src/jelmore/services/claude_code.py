"""Claude Code SDK Wrapper
Manages subprocess interactions with claude-code CLI
"""
import asyncio
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, AsyncIterator
from pathlib import Path
import structlog

from jelmore.config import get_settings

settings = get_settings()
logger = structlog.get_logger()


class ClaudeCodeSession:
    """Manages a single Claude Code session"""
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.process: Optional[asyncio.subprocess.Process] = None
        self.status = "initializing"
        self.current_directory = str(Path.cwd())
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.output_buffer = []
        self._output_queue = asyncio.Queue()
        self._monitor_task: Optional[asyncio.Task] = None
    
    async def start(self, query: str, continue_session: bool = False) -> None:
        """Start the Claude Code session with a query"""
        try:
            cmd = [settings.claude_code_bin]
            
            # Add CLI options
            cmd.extend(["--print", query])
            cmd.extend(["--output-format", "stream-json"])
            cmd.extend(["--max-turns", str(settings.claude_code_max_turns)])
            
            if continue_session and self.session_id:
                cmd.extend(["--continue"])
            
            logger.info("Starting Claude Code session", 
                       session_id=self.session_id, 
                       command=" ".join(cmd))
            
            # Start the subprocess
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
            )
            
            self.status = "active"
            self.last_activity = datetime.utcnow()
            
            # Start monitoring the output
            self._monitor_task = asyncio.create_task(self._monitor_output())
            
        except Exception as e:
            logger.error("Failed to start Claude Code session", error=str(e))
            self.status = "failed"
            raise
    
    async def _monitor_output(self) -> None:
        """Monitor and parse output from Claude Code"""
        if not self.process or not self.process.stdout:
            return
        
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    break
                
                # Decode and parse JSON output
                try:
                    output = line.decode().strip()
                    if output:
                        data = json.loads(output)
                        await self._process_output(data)
                except json.JSONDecodeError:
                    # Handle non-JSON output
                    logger.debug("Non-JSON output", output=output)
                except Exception as e:
                    logger.error("Error processing output", error=str(e))
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Monitor task error", error=str(e))
        finally:
            self.status = "idle"
    
    async def _process_output(self, data: Dict[str, Any]) -> None:
        """Process parsed output from Claude Code"""
        # Update activity timestamp
        self.last_activity = datetime.utcnow()
        
        # Check for state changes
        if data.get("type") == "system" and "waiting" in data.get("content", "").lower():
            self.status = "waiting_input"
        elif data.get("type") == "assistant":
            self.status = "active"
        
        # Check for directory changes (parse from commands)
        if data.get("type") == "tool_use" and data.get("name") == "bash":
            command = data.get("input", {}).get("command", "")
            if command.startswith("cd "):
                # Extract new directory
                new_dir = command[3:].strip()
                if not new_dir.startswith("/"):
                    new_dir = str(Path(self.current_directory) / new_dir)
                self.current_directory = str(Path(new_dir).resolve())
                logger.info("Directory changed", 
                           session_id=self.session_id,
                           new_directory=self.current_directory)
        
        # Add to output buffer
        self.output_buffer.append(data)
        if len(self.output_buffer) > settings.session_output_buffer_size:
            self.output_buffer.pop(0)
        
        # Queue for streaming
        await self._output_queue.put(data)
    
    async def send_input(self, input_text: str) -> None:
        """Send input to a waiting session"""
        if self.status != "waiting_input" or not self.process or not self.process.stdin:
            raise ValueError(f"Session not waiting for input (status: {self.status})")
        
        try:
            self.process.stdin.write(f"{input_text}\n".encode())
            await self.process.stdin.drain()
            self.status = "active"
            self.last_activity = datetime.utcnow()
            logger.info("Sent input to session", session_id=self.session_id)
        except Exception as e:
            logger.error("Failed to send input", error=str(e))
            raise
    
    async def terminate(self) -> None:
        """Terminate the Claude Code session"""
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
            
        if self._monitor_task:
            self._monitor_task.cancel()
            
        self.status = "terminated"
        logger.info("Session terminated", session_id=self.session_id)
    
    async def stream_output(self) -> AsyncIterator[Dict[str, Any]]:
        """Stream output from the session"""
        while self.status not in ["terminated", "failed"]:
            try:
                data = await asyncio.wait_for(
                    self._output_queue.get(), 
                    timeout=1.0
                )
                yield data
            except asyncio.TimeoutError:
                continue
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for API responses"""
        return {
            "id": self.session_id,
            "status": self.status,
            "current_directory": self.current_directory,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "output_buffer_size": len(self.output_buffer),
        }


class SessionManager:
    """Manages multiple Claude Code sessions"""
    
    def __init__(self):
        self.sessions: Dict[str, ClaudeCodeSession] = {}
        
    async def create_session(self, query: str) -> ClaudeCodeSession:
        """Create and start a new session"""
        session = ClaudeCodeSession()
        await session.start(query)
        self.sessions[session.session_id] = session
        logger.info("Created new session", session_id=session.session_id)
        return session
    
    def get_session(self, session_id: str) -> Optional[ClaudeCodeSession]:
        """Get a session by ID"""
        return self.sessions.get(session_id)
    
    async def terminate_session(self, session_id: str) -> bool:
        """Terminate a session"""
        session = self.sessions.get(session_id)
        if session:
            await session.terminate()
            del self.sessions[session_id]
            return True
        return False
    
    def list_sessions(self) -> list[Dict[str, Any]]:
        """List all active sessions"""
        return [session.to_dict() for session in self.sessions.values()]


# Global session manager instance
session_manager = SessionManager()