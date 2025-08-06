"""
Test configuration and fixtures
"""
import pytest
from httpx import AsyncClient
from app.main import app


@pytest.fixture
async def client():
    """Create test client"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_session_id():
    """Mock session ID for testing"""
    return "test-session-123"
