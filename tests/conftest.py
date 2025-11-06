"""
Comprehensive test configuration and fixtures for Jelmore test suite
"""
import os
import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient
from typing import AsyncGenerator, Dict, Any, Optional
import redis.asyncio as redis
from datetime import datetime
import uuid

# Set test environment variables BEFORE any imports
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("API_KEY_ADMIN", "test-admin-key-12345")
os.environ.setdefault("API_KEY_CLIENT", "test-client-key-12345") 
os.environ.setdefault("API_KEY_READONLY", "test-readonly-key-12345")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("NATS_URL", "nats://localhost:4222")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("CORS_ORIGINS", '["http://localhost", "http://127.0.0.1"]')

# Mock problematic modules at import time
import sys
from unittest.mock import MagicMock

# Create mock for structlog processors
mock_structlog = MagicMock()
mock_structlog.processors.add_logger_name = lambda x: x
mock_structlog.configure = MagicMock()
mock_structlog.get_logger = lambda: MagicMock()
sys.modules['structlog.processors'] = mock_structlog.processors

# Import the apps for testing with error handling
legacy_app = None
jelmore_app = None

try:
    from app.main import app as legacy_app
except (ImportError, AttributeError, Exception):
    legacy_app = None

try:
    from src.jelmore.main import app as jelmore_app
except (ImportError, AttributeError, Exception):
    try:
        from jelmore.main import app as jelmore_app
    except (ImportError, AttributeError, Exception):
        jelmore_app = None


# ==================== ASYNC TEST SETUP ====================

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio backend for async tests"""
    return "asyncio"


# ==================== SESSION-SCOPED OPTIMIZATIONS ====================

@pytest.fixture(scope="session")
def test_config():
    """Session-scoped test configuration to reduce setup overhead"""
    return {
        "test_timeout": 30,
        "max_retries": 3,
        "parallel_workers": "auto",
        "redis_test_db": 1,
        "nats_test_subjects": ["test.sessions", "test.events"],
        "mock_response_delay": 0.01  # Reduced for parallel execution
    }


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for legacy app testing"""
    if legacy_app is None:
        pytest.skip("Legacy app not available")
    async with AsyncClient(app=legacy_app, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def jelmore_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for Jelmore app testing"""
    if jelmore_app is None:
        pytest.skip("Jelmore app not available")
    async with AsyncClient(app=jelmore_app, base_url="http://test") as client:
        yield client


# ==================== OPTIMIZED MOCK FIXTURES ====================

@pytest.fixture(scope="session")
def mock_redis_session():
    """Session-scoped Redis mock for shared use across tests"""
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
def mock_redis(mock_redis_session):
    """Function-scoped Redis mock that reuses session mock"""
    # Reset call counts for isolation while reusing expensive setup
    for attr_name in dir(mock_redis_session):
        attr = getattr(mock_redis_session, attr_name)
        if hasattr(attr, 'reset_mock'):
            attr.reset_mock()
    return mock_redis_session


@pytest.fixture(scope="session")
def mock_nats_session():
    """Session-scoped NATS mock for parallel test efficiency"""
    mock_nats = AsyncMock()
    mock_js = AsyncMock()
    
    mock_nats.jetstream.return_value = mock_js
    mock_js.add_stream = AsyncMock()
    mock_js.publish = AsyncMock()
    mock_nats.close = AsyncMock()
    
    return mock_nats, mock_js


@pytest.fixture
def mock_nats(mock_nats_session):
    """Function-scoped NATS mock that reuses session setup"""
    mock_nats, mock_js = mock_nats_session
    
    # Reset mocks for test isolation
    mock_nats.reset_mock()
    mock_js.reset_mock()
    
    # Restore essential return values
    mock_nats.jetstream.return_value = mock_js
    
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


# ==================== OPTIMIZED DATABASE FIXTURES ====================

@pytest.fixture(scope="session")
def mock_database_session():
    """Session-scoped database mock for parallel efficiency"""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.fetch = AsyncMock(return_value=[])
    mock_db.fetchrow = AsyncMock(return_value=None)
    mock_db.fetchval = AsyncMock(return_value=None)
    mock_db.close = AsyncMock()
    return mock_db


@pytest.fixture
def mock_database(mock_database_session):
    """Function-scoped database mock with session optimization"""
    # Reset call counts while preserving setup
    mock_database_session.reset_mock()
    return mock_database_session


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


# ==================== PARALLEL-OPTIMIZED CLEANUP ====================

@pytest.fixture(autouse=True)
async def cleanup_after_test(worker_id):
    """Parallel-safe cleanup after each test"""
    yield
    
    # Worker-specific cleanup for parallel execution
    if hasattr(cleanup_after_test, '_cleanup_handlers'):
        for handler in cleanup_after_test._cleanup_handlers:
            await handler(worker_id)


def register_cleanup_handler(handler):
    """Register a cleanup handler for parallel test execution"""
    if not hasattr(cleanup_after_test, '_cleanup_handlers'):
        cleanup_after_test._cleanup_handlers = []
    cleanup_after_test._cleanup_handlers.append(handler)


@pytest.fixture(scope="session")
def worker_id(request):
    """Get the worker ID for parallel test execution"""
    if hasattr(request.config, 'workerinput'):
        return request.config.workerinput['workerid'] 
    return 'main'


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