"""
Comprehensive test configuration and fixtures for Jelmore test suite
"""
import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient
from typing import AsyncGenerator, Dict, Any, Optional
import redis.asyncio as redis
from datetime import datetime
import uuid

# Import the apps for testing
from app.main import app as legacy_app
from src.jelmore.main import app as jelmore_app


# ==================== ASYNC TEST SETUP ====================

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for legacy app testing"""
    async with AsyncClient(app=legacy_app, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def jelmore_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for Jelmore app testing"""
    async with AsyncClient(app=jelmore_app, base_url="http://test") as client:
        yield client


# ==================== MOCK FIXTURES ====================

@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    mock_redis = AsyncMock(spec=redis.Redis)
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hget = AsyncMock(return_value=None)
    mock_redis.hset = AsyncMock(return_value=1)
    mock_redis.hdel = AsyncMock(return_value=1)
    mock_redis.keys = AsyncMock(return_value=[])
    mock_redis.close = AsyncMock()
    return mock_redis


@pytest.fixture
def mock_nats():
    """Mock NATS client"""
    mock_nats = AsyncMock()
    mock_js = AsyncMock()
    
    mock_nats.jetstream.return_value = mock_js
    mock_js.add_stream = AsyncMock()
    mock_js.publish = AsyncMock()
    
    mock_nats.close = AsyncMock()
    return mock_nats, mock_js


@pytest.fixture
def mock_session_manager():
    """Mock session manager"""
    mock_manager = MagicMock()
    mock_manager.create_session = AsyncMock()
    mock_manager.get_session = MagicMock(return_value=None)
    mock_manager.terminate_session = AsyncMock(return_value=False)
    mock_manager.list_sessions = MagicMock(return_value=[])
    return mock_manager


@pytest.fixture
def mock_claude_code_session():
    """Mock Claude Code session"""
    mock_session = MagicMock()
    mock_session.session_id = "test-session-123"
    mock_session.status = "active"
    mock_session.current_directory = "/home/test"
    mock_session.created_at = datetime.utcnow()
    mock_session.last_activity = datetime.utcnow()
    mock_session.output_buffer = []
    
    mock_session.start = AsyncMock()
    mock_session.terminate = AsyncMock()
    mock_session.send_input = AsyncMock()
    mock_session.stream_output = AsyncMock()
    mock_session.to_dict = MagicMock(return_value={
        "id": "test-session-123",
        "status": "active",
        "current_directory": "/home/test",
        "created_at": datetime.utcnow().isoformat(),
        "last_activity": datetime.utcnow().isoformat(),
        "output_buffer_size": 0
    })
    
    async def mock_stream():
        yield {"type": "assistant", "content": "Test response"}
    
    mock_session.stream_output.return_value = mock_stream()
    return mock_session


# ==================== DATABASE FIXTURES ====================

@pytest.fixture
def mock_database():
    """Mock database connection"""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.fetch = AsyncMock(return_value=[])
    mock_db.fetchrow = AsyncMock(return_value=None)
    mock_db.fetchval = AsyncMock(return_value=None)
    return mock_db


@pytest.fixture
def sample_session_data():
    """Sample session data for testing"""
    return {
        "id": str(uuid.uuid4()),
        "status": "active",
        "query": "Test query for Claude Code",
        "current_directory": "/home/test/project",
        "created_at": datetime.utcnow(),
        "last_activity": datetime.utcnow(),
        "terminated_at": None,
        "metadata": {"test": True}
    }


# ==================== PROVIDER FIXTURES ====================

@pytest.fixture
def mock_base_provider():
    """Mock base provider for testing provider interface"""
    class MockProvider:
        def __init__(self, provider_type: str = "test"):
            self.provider_type = provider_type
            self.is_available = True
        
        async def create_session(self, query: str, **kwargs) -> Dict[str, Any]:
            return {
                "session_id": str(uuid.uuid4()),
                "status": "active",
                "provider": self.provider_type
            }
        
        async def terminate_session(self, session_id: str) -> bool:
            return True
        
        async def send_input(self, session_id: str, input_text: str) -> bool:
            return True
        
        def get_session_status(self, session_id: str) -> Optional[str]:
            return "active"
    
    return MockProvider()


@pytest.fixture
def mock_claude_provider(mock_base_provider):
    """Mock Claude Code provider"""
    mock_base_provider.provider_type = "claude_code"
    mock_base_provider.binary_path = "/usr/local/bin/claude"
    return mock_base_provider


@pytest.fixture  
def mock_opencode_provider(mock_base_provider):
    """Mock OpenCode provider"""  
    mock_base_provider.provider_type = "opencode"
    mock_base_provider.api_key = "test-api-key"
    return mock_base_provider


# ==================== WEBSOCKET FIXTURES ====================

@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection"""
    mock_ws = AsyncMock()
    mock_ws.accept = AsyncMock()
    mock_ws.close = AsyncMock()
    mock_ws.send_json = AsyncMock()
    mock_ws.send_text = AsyncMock()
    mock_ws.receive_json = AsyncMock()
    mock_ws.receive_text = AsyncMock()
    return mock_ws


# ==================== PERFORMANCE FIXTURES ====================

@pytest.fixture
def performance_config():
    """Configuration for performance tests"""
    return {
        "max_concurrent_sessions": 10,
        "load_test_duration": 30,
        "ramp_up_time": 5,
        "expected_response_time_ms": 500,
        "memory_limit_mb": 512
    }


# ==================== INTEGRATION TEST SETUP ====================

@pytest.fixture
def integration_config():
    """Configuration for integration tests"""
    return {
        "redis_test_url": "redis://localhost:6379/1",  # Use different DB for tests
        "nats_test_url": "nats://localhost:4222",
        "postgres_test_url": "postgresql+asyncpg://test:test@localhost:5432/test_jelmore"
    }


# ==================== TEST UTILITIES ====================

@pytest.fixture
def test_utils():
    """Utility functions for tests"""
    class TestUtils:
        @staticmethod
        def generate_session_id() -> str:
            return f"test-{uuid.uuid4()}"
        
        @staticmethod
        def create_test_query() -> str:
            return "Create a simple hello world Python script"
        
        @staticmethod
        def create_websocket_message(msg_type: str, content: Any) -> Dict[str, Any]:
            return {
                "type": msg_type,
                "content": content,
                "timestamp": datetime.utcnow().isoformat()
            }
    
    return TestUtils()


# ==================== CLEANUP FIXTURES ====================

@pytest.fixture(autouse=True)
async def cleanup_after_test():
    """Cleanup after each test"""
    yield
    # Cleanup logic here if needed
    pass


# ==================== ERROR SCENARIO FIXTURES ====================

@pytest.fixture
def error_scenarios():
    """Common error scenarios for testing"""
    return {
        "connection_timeout": ConnectionError("Connection timed out"),
        "invalid_session": ValueError("Session not found"),
        "redis_unavailable": redis.ConnectionError("Redis connection failed"),
        "nats_publish_failed": Exception("NATS publish failed"),
        "subprocess_failed": RuntimeError("Claude Code subprocess failed"),
        "permission_denied": PermissionError("Permission denied"),
        "disk_full": OSError("No space left on device")
    }


# ==================== COVERAGE TRACKING ====================

@pytest.fixture(autouse=True)
def track_coverage():
    """Automatic coverage tracking for all tests"""
    # Coverage is handled by pytest-cov configuration
    yield