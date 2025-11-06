"""Tests for Claude Code subprocess management service"""
import asyncio
import json
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from pathlib import Path

from jelmore.services.claude_code import (
    ClaudeCodeSession,
    SessionManager,
    ClaudeConfig,
    ClaudeProcessState,
    SessionMetrics,
    get_session_manager
)
from jelmore.models.session import SessionStatus


class TestClaudeConfig:
    """Test Claude CLI configuration"""
    
    def test_default_config(self):
        """Test default configuration"""
        config = ClaudeConfig()
        
        assert config.continue_session is False
        assert config.max_turns == 10
        assert config.output_format == "stream-json"
        assert config.print_mode is True
        assert config.timeout_seconds == 300
        assert config.additional_args == []
    
    def test_config_to_cli_args(self):
        """Test CLI args generation"""
        config = ClaudeConfig(
            print_mode=True,
            output_format="stream-json",
            max_turns=5,
            continue_session=True,
            working_directory="/test/dir",
            model="claude-3-sonnet",
            temperature=0.7,
            max_tokens=2000,
            system_prompt="You are a helpful assistant",
            additional_args=["--verbose"]
        )
        
        args = config.to_cli_args()
        
        expected_args = [
            "--print",
            "--output-format", "stream-json",
            "--max-turns", "5",
            "--continue",
            "--working-directory", "/test/dir",
            "--model", "claude-3-sonnet",
            "--temperature", "0.7",
            "--max-tokens", "2000",
            "--system", "You are a helpful assistant",
            "--verbose"
        ]
        
        assert args == expected_args


class TestSessionMetrics:
    """Test session metrics tracking"""
    
    def test_metrics_initialization(self):
        """Test metrics initialization"""
        start_time = datetime.utcnow()
        metrics = SessionMetrics(start_time=start_time)
        
        assert metrics.start_time == start_time
        assert metrics.end_time is None
        assert metrics.total_turns == 0
        assert metrics.messages_processed == 0
        assert metrics.errors_count == 0
        assert metrics.directory_changes == 0
        assert metrics.file_operations == 0
        assert metrics.git_operations == 0
    
    def test_duration_calculation(self):
        """Test duration calculation"""
        start_time = datetime.utcnow()
        metrics = SessionMetrics(start_time=start_time)
        
        # Test with no end time (should use current time)
        duration = metrics.duration_seconds
        assert duration >= 0
        
        # Test with specific end time
        end_time = start_time + timedelta(seconds=30)
        metrics.end_time = end_time
        assert metrics.duration_seconds == 30.0
    
    def test_metrics_to_dict(self):
        """Test metrics serialization"""
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(seconds=120)
        
        metrics = SessionMetrics(
            start_time=start_time,
            end_time=end_time,
            total_turns=5,
            messages_processed=25,
            errors_count=2,
            directory_changes=3,
            file_operations=8,
            git_operations=1
        )
        
        result = metrics.to_dict()
        
        assert result["start_time"] == start_time.isoformat()
        assert result["end_time"] == end_time.isoformat()
        assert result["duration_seconds"] == 120.0
        assert result["total_turns"] == 5
        assert result["messages_processed"] == 25
        assert result["errors_count"] == 2
        assert result["directory_changes"] == 3
        assert result["file_operations"] == 8
        assert result["git_operations"] == 1


@pytest.fixture
def mock_process():
    """Mock subprocess.Process"""
    process = Mock()
    process.pid = 12345
    process.returncode = None
    process.stdout = AsyncMock()
    process.stderr = AsyncMock()
    process.stdin = Mock()
    process.terminate = Mock()
    process.kill = Mock()
    process.wait = AsyncMock()
    return process


@pytest.fixture
def mock_session_service():
    """Mock session service"""
    service = AsyncMock()
    service.update_session_status = AsyncMock()
    return service


@pytest.fixture
def mock_publish_event():
    """Mock NATS event publishing"""
    return AsyncMock()


class TestClaudeCodeSession:
    """Test Claude Code session management"""
    
    @pytest.fixture
    def session(self):
        """Create a test session"""
        config = ClaudeConfig(working_directory="/tmp/test")
        return ClaudeCodeSession(session_id="test-session-123", config=config)
    
    def test_session_initialization(self, session):
        """Test session initialization"""
        assert session.session_id == "test-session-123"
        assert session.state == ClaudeProcessState.INITIALIZING
        assert session.process is None
        assert session.process_id is None
        assert isinstance(session.metrics, SessionMetrics)
        assert session.current_directory == "/tmp/test"
        assert session.output_buffer == []
        assert session.raw_output_buffer == []
        assert not session._shutdown_requested
        assert not session._suspended
    
    @patch('jelmore.services.claude_code.get_session_service')
    @patch('jelmore.services.claude_code.publish_event')
    @patch('asyncio.create_subprocess_exec')
    async def test_session_start_success(self, mock_subprocess, mock_publish, mock_get_service, 
                                        mock_process, mock_session_service, session):
        """Test successful session start"""
        # Setup mocks
        mock_subprocess.return_value = mock_process
        mock_get_service.return_value = mock_session_service
        mock_publish.return_value = None
        
        # Start session
        session_id = await session.start("Test query")
        
        # Verify process creation
        assert session_id == "test-session-123"
        assert session.process == mock_process
        assert session.process_id == 12345
        assert session.state == ClaudeProcessState.ACTIVE
        
        # Verify subprocess was called correctly
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args
        assert call_args[0][0] == "claude"  # Binary name
        assert "Test query" in call_args[0]  # Query in args
        
        # Verify service updates
        mock_session_service.update_session_status.assert_called()
        mock_publish.assert_called()
    
    @patch('jelmore.services.claude_code.get_session_service')
    @patch('jelmore.services.claude_code.publish_event')
    @patch('asyncio.create_subprocess_exec')
    async def test_session_start_failure(self, mock_subprocess, mock_publish, mock_get_service,
                                        mock_session_service, session):
        """Test session start failure"""
        # Setup mocks to fail
        mock_subprocess.side_effect = Exception("Failed to start process")
        mock_get_service.return_value = mock_session_service
        mock_publish.return_value = None
        
        # Attempt to start session
        with pytest.raises(RuntimeError, match="Failed to start Claude Code session"):
            await session.start("Test query")
        
        # Verify error state
        assert session.state == ClaudeProcessState.FAILED
        assert session.metrics.errors_count == 1
        
        # Verify error event was published
        mock_publish.assert_called()
        event_call = mock_publish.call_args
        assert event_call[0][0] == "session.failed"
    
    @patch('jelmore.services.claude_code.get_session_service')
    @patch('jelmore.services.claude_code.publish_event')
    async def test_continue_session(self, mock_publish, mock_get_service, 
                                   mock_process, mock_session_service, session):
        """Test session continuation with input"""
        # Setup session in waiting state
        session.process = mock_process
        session.state = ClaudeProcessState.WAITING_INPUT
        mock_get_service.return_value = mock_session_service
        mock_publish.return_value = None
        
        # Continue session with input
        session_id = await session.continue_session("User input")
        
        # Verify input was sent
        assert session_id == "test-session-123"
        assert session.state == ClaudeProcessState.ACTIVE
        assert session.metrics.total_turns == 1
        mock_process.stdin.write.assert_called_with(b"User input\n")
        mock_process.stdin.drain.assert_called()
        
        # Verify event published
        mock_publish.assert_called()
    
    async def test_continue_session_wrong_state(self, session):
        """Test continuing session in wrong state"""
        session.state = ClaudeProcessState.ACTIVE
        
        with pytest.raises(ValueError, match="Session not waiting for input"):
            await session.continue_session("User input")
    
    def test_is_alive_true(self, session, mock_process):
        """Test session is_alive when process is running"""
        session.process = mock_process
        session.state = ClaudeProcessState.ACTIVE
        mock_process.returncode = None
        
        assert session.is_alive() is True
    
    def test_is_alive_false_no_process(self, session):
        """Test session is_alive with no process"""
        assert session.is_alive() is False
    
    def test_is_alive_false_terminated(self, session, mock_process):
        """Test session is_alive when terminated"""
        session.process = mock_process
        session.state = ClaudeProcessState.TERMINATED
        mock_process.returncode = 0
        
        assert session.is_alive() is False
    
    async def test_json_output_processing(self, session):
        """Test JSON output processing"""
        # Test system message with waiting content
        system_data = {
            "type": "system",
            "content": "waiting for user input"
        }
        
        await session._process_json_output(system_data)
        assert session.state == ClaudeProcessState.WAITING_INPUT
        assert len(session.output_buffer) == 1
        
        # Test assistant message
        assistant_data = {
            "type": "assistant",
            "content": "Hello, how can I help?"
        }
        
        await session._process_json_output(assistant_data)
        assert session.state == ClaudeProcessState.ACTIVE
        assert len(session.output_buffer) == 2
    
    async def test_tool_use_processing(self, session):
        """Test tool use event processing"""
        # Test bash command
        bash_data = {
            "type": "tool_use",
            "name": "bash",
            "input": {"command": "cd /tmp"}
        }
        
        await session._process_tool_use(bash_data)
        # Directory change should be processed
        
        # Test file operation
        file_data = {
            "type": "tool_use", 
            "name": "Write",
            "input": {"file_path": "/tmp/test.txt"}
        }
        
        await session._process_tool_use(file_data)
        assert session.metrics.file_operations == 1
    
    async def test_directory_change_handling(self, session):
        """Test directory change command handling"""
        session.current_directory = "/home/user"
        
        # Test absolute path
        await session._handle_directory_change("cd /tmp")
        assert session.current_directory == "/tmp"
        assert session.metrics.directory_changes == 1
        
        # Test relative path
        await session._handle_directory_change("cd subdir")
        assert "/tmp/subdir" in session.current_directory
        assert session.metrics.directory_changes == 2
    
    async def test_bash_command_processing(self, session):
        """Test bash command processing"""
        # Test git command
        await session._process_bash_command("git status")
        assert session.metrics.git_operations == 1
        
        # Test cd command
        session.current_directory = "/home"
        await session._process_bash_command("cd /tmp")
        assert session.metrics.directory_changes == 1
    
    @patch('jelmore.services.claude_code.get_session_service')
    @patch('jelmore.services.claude_code.publish_event')
    async def test_session_terminate(self, mock_publish, mock_get_service, 
                                   mock_process, mock_session_service, session):
        """Test session termination"""
        # Setup session with process
        session.process = mock_process
        session.process_id = 12345
        session.state = ClaudeProcessState.ACTIVE
        mock_get_service.return_value = mock_session_service
        mock_publish.return_value = None
        
        # Create mock tasks
        mock_task = AsyncMock()
        mock_task.done.return_value = False
        session._monitor_task = mock_task
        session._heartbeat_task = mock_task
        session._directory_watcher_task = mock_task
        
        # Terminate session
        await session.terminate()
        
        # Verify process termination
        mock_process.terminate.assert_called()
        mock_process.wait.assert_called()
        
        # Verify state changes
        assert session.state == ClaudeProcessState.TERMINATED
        assert session._shutdown_requested is True
        assert session.metrics.end_time is not None
        
        # Verify tasks were cancelled
        mock_task.cancel.assert_called()
        
        # Verify final event published
        mock_publish.assert_called()
    
    async def test_get_status(self, session):
        """Test session status retrieval"""
        session.state = ClaudeProcessState.ACTIVE
        session.process_id = 12345
        
        status = await session.get_status()
        
        assert status["session_id"] == "test-session-123"
        assert status["state"] == "active"
        assert status["process_id"] == 12345
        assert status["current_directory"] == "/tmp/test"
        assert "created_at" in status
        assert "last_activity" in status
        assert "metrics" in status
    
    def test_to_dict(self, session):
        """Test session dictionary conversion"""
        session.state = ClaudeProcessState.ACTIVE
        session.process_id = 12345
        
        result = session.to_dict()
        
        assert result["id"] == "test-session-123"
        assert result["state"] == "active"
        assert result["status"] == "active"  # Backward compatibility
        assert result["process_id"] == 12345
        assert result["current_directory"] == "/tmp/test"
        assert "created_at" in result
        assert "metrics" in result


class TestSessionManager:
    """Test session manager"""
    
    @pytest.fixture
    async def manager(self):
        """Create test session manager"""
        mgr = SessionManager()
        await mgr.start()
        yield mgr
        await mgr.stop()
    
    async def test_manager_lifecycle(self):
        """Test manager start/stop lifecycle"""
        manager = SessionManager()
        
        # Test start
        await manager.start()
        assert manager._running is True
        assert manager._cleanup_task is not None
        
        # Test stop
        await manager.stop()
        assert manager._running is False
        assert len(manager.sessions) == 0
    
    @patch('jelmore.services.claude_code.ClaudeCodeSession')
    async def test_create_session_success(self, mock_session_class, manager):
        """Test successful session creation"""
        # Setup mock session
        mock_session = AsyncMock()
        mock_session.session_id = "test-session-456"
        mock_session.start = AsyncMock()
        mock_session_class.return_value = mock_session
        
        # Create session
        session = await manager.create_session("Test query")
        
        # Verify session creation
        assert session == mock_session
        assert "test-session-456" in manager.sessions
        mock_session.start.assert_called_with("Test query")
    
    async def test_create_session_max_limit(self, manager):
        """Test session creation at max limit"""
        # Fill manager to max capacity
        with patch('jelmore.services.claude_code.get_settings') as mock_settings:
            mock_settings.return_value.max_concurrent_sessions = 0
            
            with pytest.raises(RuntimeError, match="Maximum concurrent sessions reached"):
                await manager.create_session("Test query")
    
    async def test_get_session(self, manager):
        """Test getting session by ID"""
        # Add mock session
        mock_session = Mock()
        manager.sessions["test-id"] = mock_session
        
        # Get session
        session = manager.get_session("test-id")
        assert session == mock_session
        
        # Get non-existent session
        session = manager.get_session("non-existent")
        assert session is None
    
    async def test_terminate_session(self, manager):
        """Test session termination"""
        # Add mock session
        mock_session = AsyncMock()
        mock_session.terminate = AsyncMock()
        manager.sessions["test-id"] = mock_session
        
        # Terminate session
        result = await manager.terminate_session("test-id")
        
        # Verify termination
        assert result is True
        assert "test-id" not in manager.sessions
        mock_session.terminate.assert_called()
        
        # Test terminating non-existent session
        result = await manager.terminate_session("non-existent")
        assert result is False
    
    async def test_list_sessions(self, manager):
        """Test listing all sessions"""
        # Add mock sessions
        mock_session1 = AsyncMock()
        mock_session1.get_status = AsyncMock(return_value={"id": "session-1"})
        mock_session2 = AsyncMock()
        mock_session2.get_status = AsyncMock(return_value={"id": "session-2"})
        
        manager.sessions["session-1"] = mock_session1
        manager.sessions["session-2"] = mock_session2
        
        # List sessions
        sessions = await manager.list_sessions()
        
        # Verify list
        assert len(sessions) == 2
        assert sessions[0]["id"] == "session-1"
        assert sessions[1]["id"] == "session-2"
    
    async def test_get_session_metrics(self, manager):
        """Test session metrics aggregation"""
        # Add mock sessions
        mock_session1 = Mock()
        mock_session1.is_alive.return_value = True
        mock_session1.state.value = "active"
        mock_session1.metrics.errors_count = 2
        mock_session1.metrics.total_turns = 5
        
        mock_session2 = Mock()
        mock_session2.is_alive.return_value = False
        mock_session2.state.value = "terminated"
        mock_session2.metrics.errors_count = 1
        mock_session2.metrics.total_turns = 3
        
        manager.sessions["session-1"] = mock_session1
        manager.sessions["session-2"] = mock_session2
        
        # Get metrics
        metrics = await manager.get_session_metrics()
        
        # Verify metrics
        assert metrics["total_sessions"] == 2
        assert metrics["active_sessions"] == 1
        assert metrics["state_distribution"]["active"] == 1
        assert metrics["state_distribution"]["terminated"] == 1
        assert metrics["total_errors"] == 3
        assert metrics["total_turns"] == 8
        assert metrics["manager_running"] is True


class TestGlobalSessionManager:
    """Test global session manager functions"""
    
    @patch('jelmore.services.claude_code._session_manager', None)
    async def test_get_session_manager_creates_instance(self):
        """Test that get_session_manager creates new instance"""
        with patch('jelmore.services.claude_code.SessionManager') as mock_manager_class:
            mock_manager = AsyncMock()
            mock_manager.start = AsyncMock()
            mock_manager_class.return_value = mock_manager
            
            # Get manager (should create new instance)
            manager = await get_session_manager()
            
            # Verify instance creation
            assert manager == mock_manager
            mock_manager.start.assert_called()
    
    @patch('jelmore.services.claude_code._session_manager')
    async def test_get_session_manager_returns_existing(self, mock_existing):
        """Test that get_session_manager returns existing instance"""
        # Get manager (should return existing)
        manager = await get_session_manager()
        
        # Verify existing instance returned
        assert manager == mock_existing


@pytest.mark.integration
class TestClaudeCodeIntegration:
    """Integration tests for Claude Code subprocess management"""
    
    @pytest.fixture
    async def real_session(self):
        """Create session with real configuration"""
        config = ClaudeConfig(
            working_directory="/tmp",
            max_turns=2,
            print_mode=True,
            output_format="stream-json"
        )
        session = ClaudeCodeSession(config=config)
        yield session
        
        # Cleanup
        if session.is_alive():
            await session.terminate()
    
    @pytest.mark.skip(reason="Requires actual claude binary")
    async def test_real_session_lifecycle(self, real_session):
        """Test real session lifecycle (requires claude binary)"""
        # Start session
        session_id = await real_session.start("echo 'Hello World'")
        
        assert session_id == real_session.session_id
        assert real_session.is_alive()
        assert real_session.state == ClaudeProcessState.ACTIVE
        
        # Wait for some output
        await asyncio.sleep(2)
        
        # Check output buffer
        assert len(real_session.output_buffer) > 0
        
        # Terminate session
        await real_session.terminate()
        assert not real_session.is_alive()
        assert real_session.state == ClaudeProcessState.TERMINATED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])