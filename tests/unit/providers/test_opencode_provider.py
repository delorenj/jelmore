"""
Unit tests for OpenCode provider implementation
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import httpx
import json
import uuid
import asyncio


class OpenCodeProvider:
    """OpenCode provider implementation for testing"""
    
    def __init__(self, api_key: str, endpoint: str = "https://api.opencode.com", **config):
        self.provider_type = "opencode"
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.config = config
        self.is_available = False
        self.sessions = {}
        self.client = None
    
    async def initialize(self) -> None:
        """Initialize OpenCode provider"""
        try:
            self.client = httpx.AsyncClient(
                base_url=self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                timeout=self.config.get("timeout", 30)
            )
            
            # Test API connection
            response = await self.client.get("/health")
            self.is_available = response.status_code == 200
        except Exception:
            self.is_available = False
    
    async def create_session(self, query: str, **kwargs) -> dict:
        """Create a new OpenCode session"""
        if not self.is_available or not self.client:
            raise RuntimeError("OpenCode provider not available")
        
        session_id = str(uuid.uuid4())
        
        payload = {
            "query": query,
            "session_id": session_id,
            "model": kwargs.get("model", "gpt-4"),
            "max_tokens": kwargs.get("max_tokens", 4000),
            "temperature": kwargs.get("temperature", 0.7)
        }
        
        response = await self.client.post("/sessions", json=payload)
        
        if response.status_code != 201:
            raise RuntimeError(f"Failed to create session: {response.text}")
        
        session_data = response.json()
        
        self.sessions[session_id] = {
            "id": session_id,
            "status": "active",
            "query": query,
            "created_at": datetime.utcnow(),
            "remote_id": session_data.get("id"),
            "model": payload["model"]
        }
        
        return {
            "session_id": session_id,
            "status": "active",
            "provider": self.provider_type,
            "remote_id": session_data.get("id")
        }
    
    async def terminate_session(self, session_id: str) -> bool:
        """Terminate an OpenCode session"""
        if session_id not in self.sessions:
            return False
        
        session = self.sessions[session_id]
        remote_id = session.get("remote_id")
        
        try:
            if self.client and remote_id:
                response = await self.client.delete(f"/sessions/{remote_id}")
                if response.status_code not in [200, 204, 404]:
                    # Log error but still clean up local session
                    pass
        except Exception:
            # Continue with local cleanup even if remote fails
            pass
        
        session["status"] = "terminated"
        del self.sessions[session_id]
        return True
    
    async def send_input(self, session_id: str, input_text: str) -> bool:
        """Send input to an OpenCode session"""
        if session_id not in self.sessions or not self.client:
            return False
        
        session = self.sessions[session_id]
        remote_id = session.get("remote_id")
        
        if not remote_id:
            return False
        
        try:
            payload = {
                "message": input_text,
                "stream": self.config.get("stream", False)
            }
            
            response = await self.client.post(
                f"/sessions/{remote_id}/messages",
                json=payload
            )
            
            return response.status_code == 200
        except Exception:
            return False
    
    def get_session_status(self, session_id: str) -> str | None:
        """Get session status"""
        if session_id not in self.sessions:
            return None
        return self.sessions[session_id]["status"]
    
    async def get_session_messages(self, session_id: str) -> list:
        """Get session message history"""
        if session_id not in self.sessions or not self.client:
            return []
        
        session = self.sessions[session_id]
        remote_id = session.get("remote_id")
        
        if not remote_id:
            return []
        
        try:
            response = await self.client.get(f"/sessions/{remote_id}/messages")
            if response.status_code == 200:
                return response.json().get("messages", [])
        except Exception:
            pass
        
        return []
    
    async def cleanup(self) -> None:
        """Cleanup all sessions and close client"""
        for session_id in list(self.sessions.keys()):
            await self.terminate_session(session_id)
        
        if self.client:
            await self.client.aclose()
            self.client = None


class TestOpenCodeProvider:
    """Test suite for OpenCode provider"""
    
    @pytest.fixture
    def provider(self):
        """Create provider instance for testing"""
        return OpenCodeProvider(
            api_key="test-api-key",
            endpoint="https://api.test.com",
            timeout=10
        )
    
    @pytest.fixture
    def mock_client(self):
        """Mock HTTP client"""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        return mock_client
    
    @pytest.mark.asyncio
    async def test_provider_initialization_success(self, provider):
        """Test successful provider initialization"""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            await provider.initialize()
            
            assert provider.is_available is True
            assert provider.client is mock_client
            mock_client.get.assert_called_once_with("/health")
    
    @pytest.mark.asyncio
    async def test_provider_initialization_api_failure(self, provider):
        """Test initialization when API is unavailable"""
        mock_response = AsyncMock()
        mock_response.status_code = 500
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            await provider.initialize()
            
            assert provider.is_available is False
    
    @pytest.mark.asyncio
    async def test_provider_initialization_connection_error(self, provider):
        """Test initialization with connection error"""
        with patch('httpx.AsyncClient', side_effect=httpx.ConnectError("Connection failed")):
            await provider.initialize()
            
            assert provider.is_available is False
    
    @pytest.mark.asyncio
    async def test_create_session_success(self, provider, mock_client):
        """Test successful session creation"""
        provider.is_available = True
        provider.client = mock_client
        
        mock_response = AsyncMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "remote-123", "status": "active"}
        mock_client.post.return_value = mock_response
        
        result = await provider.create_session("Create a Python script")
        
        assert "session_id" in result
        assert result["status"] == "active"
        assert result["provider"] == "opencode"
        assert result["remote_id"] == "remote-123"
        assert len(provider.sessions) == 1
        
        # Verify API call
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/sessions"
        payload = call_args[1]["json"]
        assert payload["query"] == "Create a Python script"
        assert "session_id" in payload
    
    @pytest.mark.asyncio
    async def test_create_session_provider_unavailable(self, provider):
        """Test session creation when provider is unavailable"""
        provider.is_available = False
        
        with pytest.raises(RuntimeError, match="OpenCode provider not available"):
            await provider.create_session("Test query")
    
    @pytest.mark.asyncio
    async def test_create_session_api_error(self, provider, mock_client):
        """Test session creation with API error"""
        provider.is_available = True
        provider.client = mock_client
        
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_client.post.return_value = mock_response
        
        with pytest.raises(RuntimeError, match="Failed to create session"):
            await provider.create_session("Test query")
    
    @pytest.mark.asyncio
    async def test_create_session_with_options(self, provider, mock_client):
        """Test session creation with custom options"""
        provider.is_available = True
        provider.client = mock_client
        
        mock_response = AsyncMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "remote-123"}
        mock_client.post.return_value = mock_response
        
        await provider.create_session(
            "Test query",
            model="gpt-3.5-turbo",
            max_tokens=2000,
            temperature=0.5
        )
        
        # Verify custom options in API call
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["model"] == "gpt-3.5-turbo"
        assert payload["max_tokens"] == 2000
        assert payload["temperature"] == 0.5
    
    @pytest.mark.asyncio
    async def test_terminate_session_success(self, provider, mock_client):
        """Test successful session termination"""
        provider.is_available = True
        provider.client = mock_client
        
        # Setup session
        session_id = "test-session-123"
        provider.sessions[session_id] = {
            "id": session_id,
            "remote_id": "remote-123",
            "status": "active"
        }
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_client.delete.return_value = mock_response
        
        terminated = await provider.terminate_session(session_id)
        
        assert terminated is True
        assert session_id not in provider.sessions
        mock_client.delete.assert_called_once_with("/sessions/remote-123")
    
    @pytest.mark.asyncio
    async def test_terminate_session_not_found(self, provider):
        """Test termination of non-existent session"""
        result = await provider.terminate_session("non-existent-id")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_terminate_session_api_error(self, provider, mock_client):
        """Test termination with API error (should still succeed locally)"""
        provider.client = mock_client
        
        # Setup session
        session_id = "test-session-123"
        provider.sessions[session_id] = {
            "id": session_id,
            "remote_id": "remote-123",
            "status": "active"
        }
        
        mock_client.delete.side_effect = httpx.RequestError("Network error")
        
        terminated = await provider.terminate_session(session_id)
        
        # Should succeed locally even if remote fails
        assert terminated is True
        assert session_id not in provider.sessions
    
    @pytest.mark.asyncio
    async def test_send_input_success(self, provider, mock_client):
        """Test sending input to session"""
        provider.client = mock_client
        
        # Setup session
        session_id = "test-session-123"
        provider.sessions[session_id] = {
            "id": session_id,
            "remote_id": "remote-123",
            "status": "active"
        }
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response
        
        sent = await provider.send_input(session_id, "test input")
        
        assert sent is True
        mock_client.post.assert_called_once_with(
            "/sessions/remote-123/messages",
            json={"message": "test input", "stream": False}
        )
    
    @pytest.mark.asyncio
    async def test_send_input_session_not_found(self, provider):
        """Test sending input to non-existent session"""
        result = await provider.send_input("non-existent-id", "input")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_input_no_remote_id(self, provider, mock_client):
        """Test sending input when session has no remote ID"""
        provider.client = mock_client
        
        # Setup session without remote_id
        session_id = "test-session-123"
        provider.sessions[session_id] = {
            "id": session_id,
            "status": "active"
        }
        
        sent = await provider.send_input(session_id, "test input")
        
        assert sent is False
        mock_client.post.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_send_input_api_error(self, provider, mock_client):
        """Test sending input with API error"""
        provider.client = mock_client
        
        # Setup session
        session_id = "test-session-123"
        provider.sessions[session_id] = {
            "id": session_id,
            "remote_id": "remote-123",
            "status": "active"
        }
        
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_client.post.return_value = mock_response
        
        sent = await provider.send_input(session_id, "test input")
        
        assert sent is False
    
    def test_get_session_status_success(self, provider):
        """Test getting session status"""
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
    async def test_get_session_messages_success(self, provider, mock_client):
        """Test getting session message history"""
        provider.client = mock_client
        
        # Setup session
        session_id = "test-session-123"
        provider.sessions[session_id] = {
            "id": session_id,
            "remote_id": "remote-123",
            "status": "active"
        }
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ]
        }
        mock_client.get.return_value = mock_response
        
        messages = await provider.get_session_messages(session_id)
        
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        mock_client.get.assert_called_once_with("/sessions/remote-123/messages")
    
    @pytest.mark.asyncio
    async def test_get_session_messages_not_found(self, provider):
        """Test getting messages for non-existent session"""
        messages = await provider.get_session_messages("non-existent-id")
        assert messages == []
    
    @pytest.mark.asyncio
    async def test_cleanup_all_sessions(self, provider, mock_client):
        """Test cleanup of all sessions"""
        provider.client = mock_client
        
        # Setup multiple sessions
        for i in range(3):
            session_id = f"session-{i}"
            provider.sessions[session_id] = {
                "id": session_id,
                "remote_id": f"remote-{i}",
                "status": "active"
            }
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_client.delete.return_value = mock_response
        mock_client.aclose = AsyncMock()
        
        assert len(provider.sessions) == 3
        
        await provider.cleanup()
        
        assert len(provider.sessions) == 0
        assert mock_client.delete.call_count == 3
        mock_client.aclose.assert_called_once()
        assert provider.client is None
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, provider, mock_client):
        """Test concurrent session operations"""
        provider.is_available = True
        provider.client = mock_client
        
        mock_response = AsyncMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "remote-123"}
        mock_client.post.return_value = mock_response
        
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
    async def test_streaming_support(self, provider, mock_client):
        """Test streaming support in OpenCode provider"""
        provider.is_available = True
        provider.client = mock_client
        provider.config["stream"] = True
        
        # Setup session
        session_id = "test-session-123"
        provider.sessions[session_id] = {
            "id": session_id,
            "remote_id": "remote-123",
            "status": "active"
        }
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response
        
        await provider.send_input(session_id, "test input")
        
        # Verify stream parameter is included
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["stream"] is True
    
    @pytest.mark.asyncio
    async def test_authentication_headers(self, provider):
        """Test that authentication headers are properly set"""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            await provider.initialize()
            
            # Verify client was created with correct headers
            call_kwargs = mock_client_class.call_args[1]
            headers = call_kwargs["headers"]
            assert headers["Authorization"] == "Bearer test-api-key"
            assert headers["Content-Type"] == "application/json"
    
    @pytest.mark.asyncio
    async def test_timeout_configuration(self, provider):
        """Test timeout configuration"""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            await provider.initialize()
            
            # Verify timeout was set correctly
            call_kwargs = mock_client_class.call_args[1]
            assert call_kwargs["timeout"] == 10