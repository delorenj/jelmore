"""
API endpoint tests
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_health_check(client):
    """Test health endpoint"""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.asyncio
async def test_create_session(client):
    """Test session creation"""
    with patch("app.api.sessions.session_manager") as mock_manager:
        # Mock the session creation
        mock_session = MagicMock()
        mock_session.to_dict.return_value = {
            "id": "test-123",
            "status": "active",
            "current_directory": "/home/test",
            "created_at": "2025-08-06T12:00:00",
            "last_activity": "2025-08-06T12:00:01",
            "output_buffer_size": 0
        }
        mock_manager.create_session.return_value = mock_session
        
        response = await client.post(
            "/api/v1/session",
            json={"query": "Test query"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-123"
        assert data["status"] == "active"


@pytest.mark.asyncio
async def test_list_sessions(client):
    """Test listing sessions"""
    with patch("app.api.sessions.session_manager") as mock_manager:
        mock_manager.list_sessions.return_value = [
            {
                "id": "session-1",
                "status": "active",
                "current_directory": "/home",
                "created_at": "2025-08-06T12:00:00",
                "last_activity": "2025-08-06T12:00:01",
                "output_buffer_size": 10
            }
        ]
        
        response = await client.get("/api/v1/sessions")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "session-1"
