"""Integration Tests for Complete Jelmore API

Comprehensive integration tests covering:
- REST API endpoints with database integration
- WebSocket real-time communication
- Server-Sent Events (SSE) streaming
- Rate limiting and authentication
- Health checks and metrics
- NATS event bus integration
- Redis caching layer
- PostgreSQL persistence
"""

import pytest
import asyncio
import json
import time
from typing import Dict, Any, List
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import httpx
import websockets
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from jelmore.main_api_integrated import app
from jelmore.config import get_settings
from jelmore.models.session import Session, SessionStatus
from jelmore.services.session_service import get_session_service
from jelmore.services.database import get_session
from jelmore.services.nats import publish_event
from jelmore.api.websocket_manager import get_websocket_manager


settings = get_settings()


class TestCompleteAPIIntegration:
    """Complete API integration tests"""
    
    @pytest.fixture
    def client(self):
        """Test client with proper authentication"""
        return TestClient(app)
    
    @pytest.fixture
    def auth_headers(self):
        """Authentication headers for API calls"""
        return {
            "Authorization": "Bearer test-api-key",
            "Content-Type": "application/json"
        }
    
    @pytest.fixture
    async def session_service(self):
        """Session service instance"""
        return await get_session_service()
    
    @pytest.fixture
    async def sample_session_data(self):
        """Sample session data for testing"""
        return {
            "query": "Test query for integration testing",
            "user_id": "test-user-123",
            "current_directory": "/test/workspace",
            "metadata": {
                "test_environment": True,
                "integration_test": "complete_api"
            },
            "timeout_minutes": 30
        }
    
    def test_health_check_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]
        assert data["service"] == "jelmore-integrated-api"
        assert data["version"] == "1.0.0"
        assert "timestamp" in data
        assert "infrastructure" in data
    
    def test_metrics_endpoint(self, client):
        """Test Prometheus metrics endpoint"""
        response = client.get("/metrics")
        # Should return either metrics or 503 if prometheus not available
        assert response.status_code in [200, 503]
        
        if response.status_code == 200:
            assert response.headers["content-type"] == "text/plain; charset=utf-8"
            # Basic check for Prometheus format
            assert "jelmore_" in response.text or "# HELP" in response.text
    
    def test_system_stats_endpoint(self, client, auth_headers):
        """Test system statistics endpoint"""
        response = client.get(f"{settings.api_prefix}/v1/stats", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["service"] == "jelmore-integrated-api"
        assert data["version"] == "1.0.0"
        assert "timestamp" in data
        assert "uptime_seconds" in data
        assert "session_stats" in data
        assert "websocket_stats" in data
        assert "settings" in data
    
    def test_create_session_endpoint(self, client, auth_headers, sample_session_data):
        """Test session creation endpoint"""
        response = client.post(
            f"{settings.api_prefix}/v1/sessions",
            headers=auth_headers,
            json=sample_session_data
        )
        assert response.status_code == 201
        
        data = response.json()
        assert "session_id" in data
        assert data["status"] in ["initializing", "active"]
        assert data["query"] == sample_session_data["query"]
        assert data["user_id"] == sample_session_data["user_id"]
        assert data["current_directory"] == sample_session_data["current_directory"]
        assert data["metadata"] == sample_session_data["metadata"]
        assert "created_at" in data
        assert "updated_at" in data
        
        return data["session_id"]
    
    def test_get_session_endpoint(self, client, auth_headers, sample_session_data):
        """Test get session endpoint"""
        # First create a session
        create_response = client.post(
            f"{settings.api_prefix}/v1/sessions",
            headers=auth_headers,
            json=sample_session_data
        )
        assert create_response.status_code == 201
        session_id = create_response.json()["session_id"]
        
        # Then get the session
        response = client.get(
            f"{settings.api_prefix}/v1/sessions/{session_id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["session_id"] == session_id
        assert data["query"] == sample_session_data["query"]
        assert data["user_id"] == sample_session_data["user_id"]
    
    def test_get_nonexistent_session(self, client, auth_headers):
        """Test getting a non-existent session"""
        response = client.get(
            f"{settings.api_prefix}/v1/sessions/nonexistent-session-id",
            headers=auth_headers
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_list_sessions_endpoint(self, client, auth_headers, sample_session_data):
        """Test list sessions endpoint"""
        # Create multiple sessions
        session_ids = []
        for i in range(3):
            test_data = sample_session_data.copy()
            test_data["query"] = f"Test query {i+1}"
            test_data["user_id"] = f"test-user-{i+1}"
            
            response = client.post(
                f"{settings.api_prefix}/v1/sessions",
                headers=auth_headers,
                json=test_data
            )
            assert response.status_code == 201
            session_ids.append(response.json()["session_id"])
        
        # List all sessions
        response = client.get(
            f"{settings.api_prefix}/v1/sessions",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3
        
        # Verify our created sessions are in the list
        found_session_ids = {session["session_id"] for session in data}
        for session_id in session_ids:
            assert session_id in found_session_ids
    
    def test_list_sessions_with_filters(self, client, auth_headers, sample_session_data):
        """Test list sessions with filtering"""
        # Create session with specific user
        test_data = sample_session_data.copy()
        test_data["user_id"] = "filter-test-user"
        
        response = client.post(
            f"{settings.api_prefix}/v1/sessions",
            headers=auth_headers,
            json=test_data
        )
        assert response.status_code == 201
        session_id = response.json()["session_id"]
        
        # Filter by user_id
        response = client.get(
            f"{settings.api_prefix}/v1/sessions?user_id=filter-test-user",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        
        # All returned sessions should have the filtered user_id
        for session in data:
            assert session["user_id"] == "filter-test-user"
    
    def test_get_session_output_endpoint(self, client, auth_headers, sample_session_data):
        """Test get session output endpoint"""
        # Create session
        response = client.post(
            f"{settings.api_prefix}/v1/sessions",
            headers=auth_headers,
            json=sample_session_data
        )
        assert response.status_code == 201
        session_id = response.json()["session_id"]
        
        # Get session output
        response = client.get(
            f"{settings.api_prefix}/v1/sessions/{session_id}/output",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["session_id"] == session_id
        assert "output" in data
        assert "output_length" in data
        assert "status" in data
        assert "retrieved_at" in data
    
    def test_send_input_endpoint(self, client, auth_headers, sample_session_data):
        """Test send input to session endpoint"""
        # Create session
        response = client.post(
            f"{settings.api_prefix}/v1/sessions",
            headers=auth_headers,
            json=sample_session_data
        )
        assert response.status_code == 201
        session_id = response.json()["session_id"]
        
        # Send input
        input_data = {
            "input": "test input command",
            "metadata": {"test": True}
        }
        response = client.post(
            f"{settings.api_prefix}/v1/sessions/{session_id}/input",
            headers=auth_headers,
            json=input_data
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["message"] == "Input sent successfully"
        assert data["session_id"] == session_id
        assert data["input_length"] == len(input_data["input"])
    
    def test_send_input_to_invalid_status_session(self, client, auth_headers, sample_session_data):
        """Test sending input to session in invalid status"""
        # Create and then terminate a session
        response = client.post(
            f"{settings.api_prefix}/v1/sessions",
            headers=auth_headers,
            json=sample_session_data
        )
        assert response.status_code == 201
        session_id = response.json()["session_id"]
        
        # Terminate the session
        client.delete(
            f"{settings.api_prefix}/v1/sessions/{session_id}",
            headers=auth_headers
        )
        
        # Try to send input to terminated session
        input_data = {"input": "test input"}
        response = client.post(
            f"{settings.api_prefix}/v1/sessions/{session_id}/input",
            headers=auth_headers,
            json=input_data
        )
        assert response.status_code == 400
        assert "not waiting for input" in response.json()["detail"].lower()
    
    def test_terminate_session_endpoint(self, client, auth_headers, sample_session_data):
        """Test session termination endpoint"""
        # Create session
        response = client.post(
            f"{settings.api_prefix}/v1/sessions",
            headers=auth_headers,
            json=sample_session_data
        )
        assert response.status_code == 201
        session_id = response.json()["session_id"]
        
        # Terminate session
        response = client.delete(
            f"{settings.api_prefix}/v1/sessions/{session_id}?reason=Integration test",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["message"] == "Session terminated successfully"
        assert data["session_id"] == session_id
        assert data["reason"] == "Integration test"
        
        # Verify session is terminated
        response = client.get(
            f"{settings.api_prefix}/v1/sessions/{session_id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["terminated", "failed"]
    
    def test_terminate_nonexistent_session(self, client, auth_headers):
        """Test terminating a non-existent session"""
        response = client.delete(
            f"{settings.api_prefix}/v1/sessions/nonexistent-session-id",
            headers=auth_headers
        )
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_server_sent_events_stream(self, sample_session_data):
        """Test Server-Sent Events (SSE) streaming endpoint"""
        async with httpx.AsyncClient(app=app, base_url="http://testserver") as client:
            # Create session
            response = await client.post(
                f"{settings.api_prefix}/v1/sessions",
                headers={
                    "Authorization": "Bearer test-api-key",
                    "Content-Type": "application/json"
                },
                json=sample_session_data
            )
            assert response.status_code == 201
            session_id = response.json()["session_id"]
            
            # Connect to SSE stream
            async with client.stream(
                "GET",
                f"{settings.api_prefix}/v1/sessions/{session_id}/stream",
                headers={"Authorization": "Bearer test-api-key"}
            ) as stream:
                assert stream.status_code == 200
                assert stream.headers["content-type"] == "text/event-stream; charset=utf-8"
                
                # Read first few SSE events
                events = []
                async for chunk in stream.aiter_text():
                    if chunk.strip():
                        events.append(chunk.strip())
                        if len(events) >= 3:  # Read first 3 events
                            break
                
                # Verify we received events
                assert len(events) >= 1
                
                # First event should be connection
                connected_event = None
                for event in events:
                    if "event: connected" in event:
                        connected_event = event
                        break
                
                assert connected_event is not None
                assert session_id in connected_event
    
    @pytest.mark.asyncio 
    async def test_websocket_connection_and_messaging(self, sample_session_data):
        """Test WebSocket connection and bidirectional messaging"""
        # Create session first
        async with httpx.AsyncClient(app=app, base_url="http://testserver") as client:
            response = await client.post(
                f"{settings.api_prefix}/v1/sessions",
                headers={
                    "Authorization": "Bearer test-api-key",
                    "Content-Type": "application/json"
                },
                json=sample_session_data
            )
            assert response.status_code == 201
            session_id = response.json()["session_id"]
        
        # Connect to WebSocket
        ws_url = f"ws://testserver{settings.api_prefix}/v1/sessions/{session_id}/ws"
        
        # Note: In real integration tests, you'd need a running server
        # This is a simplified test structure
        async with websockets.connect(ws_url) as websocket:
            # Should receive initial connection message
            message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data = json.loads(message)
            assert data["event"] == "session_info"
            assert data["session_id"] == session_id
            
            # Send a ping message
            await websocket.send(json.dumps({
                "type": "ping"
            }))
            
            # Should receive pong response
            message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data = json.loads(message)
            assert data["event"] == "pong"
            
            # Send input message
            await websocket.send(json.dumps({
                "type": "input",
                "content": "test websocket input"
            }))
            
            # Should receive input acknowledgment
            message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data = json.loads(message)
            assert data["event"] == "input_received"
            assert data["content"] == "test websocket input"
    
    def test_authentication_required(self, client, sample_session_data):
        """Test that authentication is required for protected endpoints"""
        # Try to create session without auth
        response = client.post(
            f"{settings.api_prefix}/v1/sessions",
            json=sample_session_data
        )
        assert response.status_code == 401
        
        # Try with invalid auth
        response = client.post(
            f"{settings.api_prefix}/v1/sessions",
            headers={"Authorization": "Bearer invalid-key"},
            json=sample_session_data
        )
        assert response.status_code == 401
    
    def test_request_validation(self, client, auth_headers):
        """Test request validation for API endpoints"""
        # Test invalid session creation data
        invalid_data = {
            "query": "",  # Empty query should be invalid
            "timeout_minutes": -1  # Negative timeout should be invalid
        }
        response = client.post(
            f"{settings.api_prefix}/v1/sessions",
            headers=auth_headers,
            json=invalid_data
        )
        assert response.status_code == 422  # Validation error
    
    def test_cors_headers(self, client):
        """Test CORS headers are properly set"""
        response = client.options("/health")
        assert response.status_code == 200
        
        # Check for CORS headers
        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers
        assert "access-control-allow-headers" in response.headers
    
    @pytest.mark.asyncio
    async def test_database_integration(self, sample_session_data, session_service):
        """Test database integration and persistence"""
        # Create session via service
        session_id = await session_service.create_session(
            query=sample_session_data["query"],
            user_id=sample_session_data["user_id"],
            metadata=sample_session_data["metadata"],
            current_directory=sample_session_data["current_directory"]
        )
        
        # Verify session exists in database
        session_data = await session_service.get_session(session_id)
        assert session_data is not None
        assert session_data["session_id"] == session_id
        assert session_data["query"] == sample_session_data["query"]
        
        # Update session status
        success = await session_service.update_session_status(
            session_id,
            SessionStatus.ACTIVE,
            output_data="Test output data"
        )
        assert success is True
        
        # Verify update persisted
        updated_session = await session_service.get_session(session_id)
        assert updated_session["status"] == SessionStatus.ACTIVE.value
        assert "Test output data" in updated_session.get("output_buffer", "")
    
    @pytest.mark.asyncio
    async def test_event_bus_integration(self, sample_session_data):
        """Test NATS event bus integration"""
        # Mock NATS publish to verify events are sent
        with patch('jelmore.services.nats.publish_event') as mock_publish:
            mock_publish.return_value = True
            
            # Create session which should publish event
            session_service = await get_session_service()
            session_id = await session_service.create_session(
                query=sample_session_data["query"],
                user_id=sample_session_data["user_id"]
            )
            
            # Verify event was published
            mock_publish.assert_called()
            
            # Check the call arguments
            call_args = mock_publish.call_args
            assert "SESSION_CREATED" in str(call_args) or "session.created" in str(call_args)
            assert session_id in str(call_args)
    
    @pytest.mark.asyncio
    async def test_websocket_manager_integration(self):
        """Test WebSocket manager integration"""
        ws_manager = await get_websocket_manager()
        
        # Test manager stats
        stats = await ws_manager.get_stats()
        assert "total_connections" in stats
        assert "sessions_with_connections" in stats
        assert "manager_running" in stats
        
        # Test broadcasting (with no connections, should not fail)
        sent_count = await ws_manager.broadcast_to_all({
            "event": "test_broadcast",
            "message": "integration test"
        })
        assert sent_count == 0  # No connections, so 0 sent
    
    def test_api_versioning(self, client, auth_headers):
        """Test API versioning is properly implemented"""
        # All our endpoints should be under /v1
        response = client.get(f"{settings.api_prefix}/v1/stats", headers=auth_headers)
        assert response.status_code == 200
        
        # Non-versioned endpoints should not exist
        response = client.get(f"{settings.api_prefix}/stats", headers=auth_headers)
        assert response.status_code == 404
    
    def test_error_handling_and_logging(self, client, auth_headers):
        """Test proper error handling and response formatting"""
        # Test 404 error
        response = client.get(
            f"{settings.api_prefix}/v1/sessions/invalid-session-id",
            headers=auth_headers
        )
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()
        
        # Test 422 validation error
        response = client.post(
            f"{settings.api_prefix}/v1/sessions",
            headers=auth_headers,
            json={"invalid": "data"}  # Missing required fields
        )
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
    
    def test_performance_and_response_times(self, client, auth_headers, sample_session_data):
        """Test API performance and reasonable response times"""
        # Health check should be fast
        start_time = time.time()
        response = client.get("/health")
        health_time = time.time() - start_time
        
        assert response.status_code == 200
        assert health_time < 1.0  # Should respond within 1 second
        
        # Session creation should be reasonably fast
        start_time = time.time()
        response = client.post(
            f"{settings.api_prefix}/v1/sessions",
            headers=auth_headers,
            json=sample_session_data
        )
        creation_time = time.time() - start_time
        
        assert response.status_code == 201
        assert creation_time < 5.0  # Should create within 5 seconds
    
    def test_concurrent_requests(self, client, auth_headers, sample_session_data):
        """Test handling of concurrent requests"""
        import threading
        import queue
        
        results = queue.Queue()
        
        def create_session(session_num):
            try:
                test_data = sample_session_data.copy()
                test_data["query"] = f"Concurrent test session {session_num}"
                test_data["user_id"] = f"concurrent-user-{session_num}"
                
                response = client.post(
                    f"{settings.api_prefix}/v1/sessions",
                    headers=auth_headers,
                    json=test_data
                )
                results.put((session_num, response.status_code, response.json()))
            except Exception as e:
                results.put((session_num, 500, {"error": str(e)}))
        
        # Create 5 concurrent sessions
        threads = []
        for i in range(5):
            thread = threading.Thread(target=create_session, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=10)
        
        # Check results
        successful_creations = 0
        while not results.empty():
            session_num, status_code, data = results.get()
            if status_code == 201:
                successful_creations += 1
                assert "session_id" in data
        
        # All concurrent requests should succeed
        assert successful_creations == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])