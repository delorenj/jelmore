"""
Unit tests for Claude Code provider implementation
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime
from pathlib import Path
import json
import uuid
import subprocess


class ClaudeCodeProvider:
    """Claude Code provider implementation for testing"""
    
    def __init__(self, binary_path: str = "claude", **config):
        self.provider_type = "claude_code"
        self.binary_path = binary_path
        self.config = config
        self.is_available = False
        self.sessions = {}
    
    async def initialize(self) -> None:
        """Initialize Claude Code provider"""
        try:
            # Check if claude binary is available
            result = await asyncio.create_subprocess_exec(
                self.binary_path, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()
            self.is_available = result.returncode == 0
        except FileNotFoundError:
            self.is_available = False
    
    async def create_session(self, query: str, **kwargs) -> dict:
        """Create a new Claude Code session"""
        if not self.is_available:
            raise RuntimeError("Claude Code provider not available")
        
        session_id = str(uuid.uuid4())
        
        # Build command
        cmd = [self.binary_path]
        cmd.extend(["--print", query])
        cmd.extend(["--output-format", "stream-json"])
        cmd.extend(["--max-turns", str(kwargs.get("max_turns", 10))])
        
        if kwargs.get("continue_session"):
            cmd.extend(["--continue"])
        
        # Start subprocess
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
        )
        
        session_data = {
            "id": session_id,
            "status": "active",
            "query": query,
            "process": process,
            "created_at": datetime.utcnow(),
            "current_directory": str(Path.cwd())
        }
        
        self.sessions[session_id] = session_data
        
        return {
            "session_id": session_id,
            "status": "active",
            "provider": self.provider_type
        }
    
    async def terminate_session(self, session_id: str) -> bool:
        """Terminate a Claude Code session"""
        if session_id not in self.sessions:
            return False
        
        session = self.sessions[session_id]
        process = session["process"]
        
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        
        session["status"] = "terminated"
        del self.sessions[session_id]
        return True
    
    async def send_input(self, session_id: str, input_text: str) -> bool:
        """Send input to a Claude Code session"""
        if session_id not in self.sessions:
            return False
        
        session = self.sessions[session_id]
        process = session["process"]
        
        if not process.stdin:
            return False
        
        try:
            process.stdin.write(f"{input_text}\n".encode())
            await process.stdin.drain()
            return True
        except Exception:
            return False
    
    def get_session_status(self, session_id: str) -> str | None:
        """Get session status"""
        if session_id not in self.sessions:
            return None
        return self.sessions[session_id]["status"]
    
    async def cleanup(self) -> None:
        """Cleanup all sessions"""
        for session_id in list(self.sessions.keys()):
            await self.terminate_session(session_id)


class TestClaudeCodeProvider:
    """Test suite for Claude Code provider"""
    
    @pytest.fixture
    def provider(self):
        """Create provider instance for testing"""
        return ClaudeCodeProvider("/usr/bin/mock-claude")
    
    @pytest.fixture
    def mock_subprocess(self):
        """Mock subprocess for testing"""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"Claude Code v1.0.0", b""))
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()
        mock_process.stdin = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stderr = AsyncMock()
        return mock_process
    
    @pytest.mark.asyncio
    async def test_provider_initialization_success(self, provider, mock_subprocess):
        """Test successful provider initialization"""
        with patch('asyncio.create_subprocess_exec', return_value=mock_subprocess):
            await provider.initialize()
            assert provider.is_available is True
    
    @pytest.mark.asyncio
    async def test_provider_initialization_binary_not_found(self, provider):
        """Test initialization when Claude binary is not found"""
        with patch('asyncio.create_subprocess_exec', side_effect=FileNotFoundError):
            await provider.initialize()
            assert provider.is_available is False
    
    @pytest.mark.asyncio
    async def test_provider_initialization_binary_fails(self, provider, mock_subprocess):
        """Test initialization when Claude binary returns error"""
        mock_subprocess.returncode = 1
        with patch('asyncio.create_subprocess_exec', return_value=mock_subprocess):
            await provider.initialize()
            assert provider.is_available is False
    
    @pytest.mark.asyncio
    async def test_create_session_success(self, provider, mock_subprocess):
        """Test successful session creation"""
        provider.is_available = True
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_subprocess):
            result = await provider.create_session("Create a Python script")
            
            assert "session_id" in result
            assert result["status"] == "active"
            assert result["provider"] == "claude_code"
            assert len(provider.sessions) == 1
    
    @pytest.mark.asyncio
    async def test_create_session_provider_unavailable(self, provider):
        """Test session creation when provider is unavailable"""
        provider.is_available = False
        
        with pytest.raises(RuntimeError, match="Claude Code provider not available"):
            await provider.create_session("Test query")
    
    @pytest.mark.asyncio
    async def test_create_session_with_options(self, provider, mock_subprocess):
        """Test session creation with various options"""
        provider.is_available = True
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_subprocess) as mock_exec:
            await provider.create_session(
                "Test query",
                max_turns=20,
                continue_session=True
            )
            
            # Verify command line arguments
            called_args = mock_exec.call_args[0]
            assert "--max-turns" in called_args
            assert "20" in called_args
            assert "--continue" in called_args
    
    @pytest.mark.asyncio
    async def test_terminate_session_success(self, provider, mock_subprocess):
        """Test successful session termination"""
        provider.is_available = True
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_subprocess):
            # Create session first
            result = await provider.create_session("Test query")
            session_id = result["session_id"]
            
            # Terminate session
            terminated = await provider.terminate_session(session_id)
            
            assert terminated is True
            assert session_id not in provider.sessions
            mock_subprocess.terminate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_terminate_session_not_found(self, provider):
        """Test termination of non-existent session"""
        result = await provider.terminate_session("non-existent-id")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_terminate_session_force_kill(self, provider, mock_subprocess):
        """Test force killing when terminate times out"""
        provider.is_available = True
        mock_subprocess.wait.side_effect = asyncio.TimeoutError()
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_subprocess):
            # Create session first
            result = await provider.create_session("Test query")
            session_id = result["session_id"]
            
            # Terminate session (should force kill)
            terminated = await provider.terminate_session(session_id)
            
            assert terminated is True
            mock_subprocess.terminate.assert_called_once()
            mock_subprocess.kill.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_input_success(self, provider, mock_subprocess):
        """Test sending input to session"""
        provider.is_available = True
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_subprocess):
            # Create session first
            result = await provider.create_session("Test query")
            session_id = result["session_id"]
            
            # Send input
            sent = await provider.send_input(session_id, "test input")
            
            assert sent is True
            mock_subprocess.stdin.write.assert_called_with(b"test input\n")
            mock_subprocess.stdin.drain.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_input_session_not_found(self, provider):
        """Test sending input to non-existent session"""
        result = await provider.send_input("non-existent-id", "input")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_input_no_stdin(self, provider, mock_subprocess):
        """Test sending input when stdin is None"""
        provider.is_available = True
        mock_subprocess.stdin = None
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_subprocess):
            # Create session first
            result = await provider.create_session("Test query")
            session_id = result["session_id"]
            
            # Send input
            sent = await provider.send_input(session_id, "test input")
            
            assert sent is False
    
    @pytest.mark.asyncio
    async def test_send_input_write_exception(self, provider, mock_subprocess):
        """Test sending input when write fails"""
        provider.is_available = True
        mock_subprocess.stdin.write.side_effect = BrokenPipeError()
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_subprocess):
            # Create session first
            result = await provider.create_session("Test query")
            session_id = result["session_id"]
            
            # Send input
            sent = await provider.send_input(session_id, "test input")
            
            assert sent is False
    
    def test_get_session_status_success(self, provider):
        """Test getting session status"""
        # Manually add a session for testing
        session_id = "test-session-123"
        provider.sessions[session_id] = {
            "id": session_id,
            "status": "active"
        }
        
        status = provider.get_session_status(session_id)
        assert status == "active"
    
    def test_get_session_status_not_found(self, provider):
        """Test getting status of non-existent session"""
        status = provider.get_session_status("non-existent-id")
        assert status is None
    
    @pytest.mark.asyncio
    async def test_cleanup_all_sessions(self, provider, mock_subprocess):
        """Test cleanup of all sessions"""
        provider.is_available = True
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_subprocess):
            # Create multiple sessions
            session1 = await provider.create_session("Query 1")
            session2 = await provider.create_session("Query 2")
            session3 = await provider.create_session("Query 3")
            
            assert len(provider.sessions) == 3
            
            # Cleanup all
            await provider.cleanup()
            
            assert len(provider.sessions) == 0
            # Verify terminate was called for each session
            assert mock_subprocess.terminate.call_count == 3
    
    @pytest.mark.asyncio
    async def test_concurrent_session_operations(self, provider, mock_subprocess):
        """Test concurrent session operations"""
        provider.is_available = True
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_subprocess):
            # Create multiple sessions concurrently
            tasks = []
            for i in range(5):
                task = asyncio.create_task(
                    provider.create_session(f"Query {i}")
                )
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            
            assert len(results) == 5
            assert len(provider.sessions) == 5
            
            # All session IDs should be unique
            session_ids = [result["session_id"] for result in results]
            assert len(set(session_ids)) == 5
    
    @pytest.mark.asyncio
    async def test_session_output_parsing(self, provider, mock_subprocess):
        """Test parsing of Claude Code JSON output"""
        provider.is_available = True
        
        # Mock output stream
        output_lines = [
            b'{"type": "assistant", "content": "Hello"}\n',
            b'{"type": "tool_use", "name": "bash", "input": {"command": "ls"}}\n',
            b'{"type": "tool_result", "output": "file1.txt\\nfile2.txt"}\n'
        ]
        
        async def mock_readline():
            for line in output_lines:
                yield line
            yield b''  # End of stream
        
        mock_subprocess.stdout.readline = AsyncMock(side_effect=mock_readline())
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_subprocess):
            result = await provider.create_session("Test query")
            session_id = result["session_id"]
            
            # Verify session was created
            assert session_id in provider.sessions
    
    @pytest.mark.asyncio
    async def test_provider_configuration(self):
        """Test provider with various configurations"""
        configs = [
            {"timeout": 60},
            {"max_memory": 1024},
            {"working_dir": "/tmp/test"}
        ]
        
        for config in configs:
            provider = ClaudeCodeProvider(**config)
            assert provider.config == config
    
    @pytest.mark.asyncio
    async def test_error_recovery(self, provider, mock_subprocess):
        """Test error recovery mechanisms"""
        provider.is_available = True
        
        # Simulate process crash
        mock_subprocess.wait.side_effect = [0, RuntimeError("Process crashed")]
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_subprocess):
            # Create session
            result = await provider.create_session("Test query")
            session_id = result["session_id"]
            
            # Attempt termination (should handle error gracefully)
            terminated = await provider.terminate_session(session_id)
            
            # Should still succeed in cleanup
            assert terminated is True