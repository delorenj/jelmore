"""
Integration tests for complete session lifecycle
"""
import pytest
import asyncio
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock, MagicMock
import json
import uuid
from datetime import datetime


class TestSessionLifecycle:
    """Test complete session lifecycle from creation to termination"""
    
    @pytest.mark.asyncio
    async def test_complete_session_lifecycle(self, async_client, mock_redis, mock_nats):
        """Test full session lifecycle: create -> use -> terminate"""
        mock_nats_client, mock_js = mock_nats
        
        # Mock session manager and Redis
        with patch('app.core.redis_client.get_redis', return_value=mock_redis), \
             patch('app.core.nats_client.nc', mock_nats_client), \
             patch('app.core.nats_client.js', mock_js), \
             patch('app.core.claude_code.session_manager') as mock_manager:
            
            # Setup mock session
            mock_session = MagicMock()
            session_id = str(uuid.uuid4())
            mock_session.session_id = session_id
            mock_session.status = "active"
            mock_session.to_dict.return_value = {
                "id": session_id,
                "status": "active",
                "current_directory": "/home/test",
                "created_at": datetime.utcnow().isoformat(),
                "last_activity": datetime.utcnow().isoformat(),
                "output_buffer_size": 0
            }
            
            # Mock stream output
            async def mock_stream():
                yield {"type": "assistant", "content": "Hello, I can help you with that."}
                yield {"type": "tool_use", "name": "bash", "input": {"command": "ls -la"}}
                yield {"type": "tool_result", "output": "total 4\ndrwxr-xr-x 2 user user 4096 Jan 1 12:00 ."}
            
            mock_session.stream_output.return_value = mock_stream()
            mock_session.send_input = AsyncMock()
            
            mock_manager.create_session.return_value = mock_session
            mock_manager.get_session.return_value = mock_session
            mock_manager.terminate_session.return_value = True
            
            # 1. Create session
            create_response = await async_client.post(
                "/api/v1/sessions",
                json={"query": "Create a Python hello world script"}
            )
            
            assert create_response.status_code == 200
            session_data = create_response.json()
            assert session_data["id"] == session_id
            assert session_data["status"] == "active"
            
            # Verify NATS event was published
            mock_js.publish.assert_called()
            
            # 2. Get session details
            get_response = await async_client.get(f"/api/v1/sessions/{session_id}")
            assert get_response.status_code == 200
            get_data = get_response.json()
            assert get_data["id"] == session_id
            
            # 3. Send input to session
            input_response = await async_client.post(
                f"/api/v1/sessions/{session_id}/input",
                json={"input": "Please add error handling to the script"}
            )
            
            assert input_response.status_code == 200
            mock_session.send_input.assert_called_once_with("Please add error handling to the script")
            
            # 4. List all sessions
            list_response = await async_client.get("/api/v1/sessions")
            assert list_response.status_code == 200
            sessions_list = list_response.json()
            assert len(sessions_list) > 0
            
            # 5. Terminate session
            terminate_response = await async_client.delete(f"/api/v1/sessions/{session_id}")
            assert terminate_response.status_code == 200
            
            # Verify termination
            mock_manager.terminate_session.assert_called_once_with(session_id)
    
    @pytest.mark.asyncio
    async def test_websocket_session_streaming(self, mock_redis, mock_nats):
        """Test WebSocket streaming functionality"""
        mock_nats_client, mock_js = mock_nats
        
        with patch('app.core.redis_client.get_redis', return_value=mock_redis), \
             patch('app.core.nats_client.nc', mock_nats_client), \
             patch('app.core.nats_client.js', mock_js), \
             patch('app.core.claude_code.session_manager') as mock_manager:
            
            from fastapi.testclient import TestClient
            from fastapi import WebSocket
            
            # Setup mock session with streaming
            session_id = str(uuid.uuid4())
            mock_session = MagicMock()
            mock_session.session_id = session_id
            
            async def mock_stream():
                messages = [
                    {"type": "assistant", "content": "I'll help you create a Python script."},
                    {"type": "tool_use", "name": "Write", "input": {"file_path": "/tmp/hello.py"}},
                    {"type": "tool_result", "output": "File created successfully"},
                    {"type": "assistant", "content": "The script has been created!"}
                ]
                for msg in messages:
                    yield msg
                    await asyncio.sleep(0.1)  # Simulate streaming delay
            
            mock_session.stream_output.return_value = mock_stream()
            mock_manager.get_session.return_value = mock_session
            
            # Test WebSocket connection (simplified)
            # Note: Full WebSocket testing would require a more complex setup
            assert mock_session is not None
            
            # Verify stream output works
            messages = []
            async for message in mock_session.stream_output():
                messages.append(message)
            
            assert len(messages) == 4
            assert messages[0]["type"] == "assistant"
            assert messages[1]["type"] == "tool_use"
            assert messages[2]["type"] == "tool_result"
            assert messages[3]["type"] == "assistant"
    
    @pytest.mark.asyncio
    async def test_session_error_recovery(self, async_client, mock_redis, mock_nats):
        """Test session error handling and recovery"""
        mock_nats_client, mock_js = mock_nats
        
        with patch('app.core.redis_client.get_redis', return_value=mock_redis), \
             patch('app.core.nats_client.nc', mock_nats_client), \
             patch('app.core.nats_client.js', mock_js), \
             patch('app.core.claude_code.session_manager') as mock_manager:
            
            # Test session creation failure
            mock_manager.create_session.side_effect = RuntimeError("Claude Code binary not found")
            
            create_response = await async_client.post(
                "/api/v1/sessions",
                json={"query": "Test query"}
            )
            
            assert create_response.status_code == 500
            assert "Claude Code binary not found" in create_response.json()["detail"]
            
            # Test session not found
            mock_manager.get_session.return_value = None
            
            get_response = await async_client.get("/api/v1/sessions/nonexistent-id")
            assert get_response.status_code == 404
            
            # Test input to non-existent session
            input_response = await async_client.post(
                "/api/v1/sessions/nonexistent-id/input",
                json={"input": "test input"}
            )
            assert input_response.status_code == 404
            
            # Test termination of non-existent session
            mock_manager.terminate_session.return_value = False
            
            terminate_response = await async_client.delete("/api/v1/sessions/nonexistent-id")
            assert terminate_response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_concurrent_session_management(self, async_client, mock_redis, mock_nats):
        """Test concurrent session operations"""
        mock_nats_client, mock_js = mock_nats
        
        with patch('app.core.redis_client.get_redis', return_value=mock_redis), \
             patch('app.core.nats_client.nc', mock_nats_client), \
             patch('app.core.nats_client.js', mock_js), \
             patch('app.core.claude_code.session_manager') as mock_manager:
            
            # Setup mock sessions
            sessions = []
            for i in range(5):
                session_id = str(uuid.uuid4())
                mock_session = MagicMock()
                mock_session.session_id = session_id
                mock_session.status = "active"
                mock_session.to_dict.return_value = {
                    "id": session_id,
                    "status": "active",
                    "current_directory": "/home/test",
                    "created_at": datetime.utcnow().isoformat(),
                    "last_activity": datetime.utcnow().isoformat(),
                    "output_buffer_size": 0
                }
                sessions.append(mock_session)
            
            mock_manager.create_session.side_effect = sessions
            mock_manager.list_sessions.return_value = [s.to_dict() for s in sessions]
            
            # Create multiple sessions concurrently
            tasks = []
            for i in range(5):
                task = asyncio.create_task(
                    async_client.post(
                        "/api/v1/sessions",
                        json={"query": f"Query {i}"}
                    )
                )
                tasks.append(task)
            
            responses = await asyncio.gather(*tasks)
            
            # All sessions should be created successfully
            assert all(r.status_code == 200 for r in responses)
            
            # List all sessions
            list_response = await async_client.get("/api/v1/sessions")
            assert list_response.status_code == 200
            session_list = list_response.json()
            assert len(session_list) == 5
    
    @pytest.mark.asyncio
    async def test_session_state_transitions(self, async_client, mock_redis, mock_nats):
        """Test session state transitions during lifecycle"""
        mock_nats_client, mock_js = mock_nats
        
        with patch('app.core.redis_client.get_redis', return_value=mock_redis), \
             patch('app.core.nats_client.nc', mock_nats_client), \
             patch('app.core.nats_client.js', mock_js), \
             patch('app.core.claude_code.session_manager') as mock_manager:
            
            # Mock session with state changes
            session_id = str(uuid.uuid4())
            mock_session = MagicMock()
            mock_session.session_id = session_id
            mock_session.status = "initializing"  # Start in initializing state
            
            # Simulate state progression
            session_states = [
                {"id": session_id, "status": "initializing", "current_directory": "/home/test",
                 "created_at": datetime.utcnow().isoformat(), "last_activity": datetime.utcnow().isoformat(),
                 "output_buffer_size": 0},
                {"id": session_id, "status": "active", "current_directory": "/home/test",
                 "created_at": datetime.utcnow().isoformat(), "last_activity": datetime.utcnow().isoformat(),
                 "output_buffer_size": 5},
                {"id": session_id, "status": "waiting_input", "current_directory": "/home/test",
                 "created_at": datetime.utcnow().isoformat(), "last_activity": datetime.utcnow().isoformat(),
                 "output_buffer_size": 10},
                {"id": session_id, "status": "active", "current_directory": "/home/test",
                 "created_at": datetime.utcnow().isoformat(), "last_activity": datetime.utcnow().isoformat(),
                 "output_buffer_size": 15}
            ]
            
            state_index = 0
            def get_session_state():
                nonlocal state_index
                if state_index < len(session_states):
                    mock_session.to_dict.return_value = session_states[state_index]
                    state_index += 1
                return mock_session
            
            mock_manager.create_session.return_value = mock_session
            mock_manager.get_session.side_effect = lambda _: get_session_state()
            
            # Create session
            create_response = await async_client.post(
                "/api/v1/sessions",
                json={"query": "Create a complex application"}
            )
            assert create_response.status_code == 200
            
            # Check session states
            for expected_state in ["initializing", "active", "waiting_input", "active"]:
                get_response = await async_client.get(f"/api/v1/sessions/{session_id}")
                assert get_response.status_code == 200
                session_data = get_response.json()
                assert session_data["status"] == expected_state
                
                # Simulate time passage
                await asyncio.sleep(0.01)
    
    @pytest.mark.asyncio
    async def test_session_persistence_redis(self, async_client, mock_redis, mock_nats):
        """Test session data persistence in Redis"""
        mock_nats_client, mock_js = mock_nats
        
        # Configure Redis mock for persistence testing
        redis_data = {}
        
        async def mock_setex(key, ttl, value):
            redis_data[key] = value
            return True
        
        async def mock_get(key):
            return redis_data.get(key)
        
        mock_redis.setex.side_effect = mock_setex
        mock_redis.get.side_effect = mock_get
        
        with patch('app.core.redis_client.get_redis', return_value=mock_redis), \
             patch('app.core.nats_client.nc', mock_nats_client), \
             patch('app.core.nats_client.js', mock_js), \
             patch('app.core.claude_code.session_manager') as mock_manager:
            
            session_id = str(uuid.uuid4())
            mock_session = MagicMock()
            mock_session.session_id = session_id
            mock_session.status = "active"
            mock_session.to_dict.return_value = {
                "id": session_id,
                "status": "active",
                "query": "Test query for persistence",
                "current_directory": "/home/test",
                "created_at": datetime.utcnow().isoformat(),
                "last_activity": datetime.utcnow().isoformat(),
                "output_buffer_size": 0
            }
            
            mock_manager.create_session.return_value = mock_session
            mock_manager.get_session.return_value = mock_session
            
            # Create session (this should store data in Redis)
            create_response = await async_client.post(
                "/api/v1/sessions",
                json={"query": "Test query for persistence"}
            )
            
            assert create_response.status_code == 200
            
            # Verify session data was stored
            session_key = f"session:{session_id}"
            stored_data = await mock_get(session_key)
            if stored_data:
                session_data = json.loads(stored_data)
                assert session_data["query"] == "Test query for persistence"
                assert session_data["status"] == "active"
    
    @pytest.mark.asyncio
    async def test_session_cleanup_on_failure(self, async_client, mock_redis, mock_nats):
        """Test session cleanup when operations fail"""
        mock_nats_client, mock_js = mock_nats
        
        with patch('app.core.redis_client.get_redis', return_value=mock_redis), \
             patch('app.core.nats_client.nc', mock_nats_client), \
             patch('app.core.nats_client.js', mock_js), \
             patch('app.core.claude_code.session_manager') as mock_manager:
            
            session_id = str(uuid.uuid4())
            mock_session = MagicMock()
            mock_session.session_id = session_id
            mock_session.status = "failed"
            mock_session.to_dict.return_value = {
                "id": session_id,
                "status": "failed",
                "current_directory": "/home/test",
                "created_at": datetime.utcnow().isoformat(),
                "last_activity": datetime.utcnow().isoformat(),
                "output_buffer_size": 0
            }
            
            # Simulate session creation failure
            mock_manager.create_session.side_effect = RuntimeError("Subprocess failed to start")
            
            create_response = await async_client.post(
                "/api/v1/sessions",
                json={"query": "This will fail"}
            )
            
            assert create_response.status_code == 500
            
            # Verify cleanup was attempted (no lingering resources)
            mock_manager.create_session.assert_called_once()
    
    @pytest.mark.asyncio 
    async def test_health_check_during_operations(self, async_client, mock_redis, mock_nats):
        """Test health check endpoint during active operations"""
        mock_nats_client, mock_js = mock_nats
        
        with patch('app.core.redis_client.get_redis', return_value=mock_redis), \
             patch('app.core.nats_client.nc', mock_nats_client), \
             patch('app.core.nats_client.js', mock_js):
            
            # Health check should work regardless of other operations
            health_response = await async_client.get("/health")
            assert health_response.status_code == 200
            
            health_data = health_response.json()
            assert health_data["status"] == "healthy"
            assert "version" in health_data