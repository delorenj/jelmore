"""
Unit tests for base provider interface and abstract provider contract
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import uuid


class BaseProvider(ABC):
    """Abstract base class for all provider implementations"""
    
    def __init__(self, provider_type: str, **config):
        self.provider_type = provider_type
        self.config = config
        self.is_available = False
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the provider"""
        pass
    
    @abstractmethod
    async def create_session(self, query: str, **kwargs) -> Dict[str, Any]:
        """Create a new session"""
        pass
    
    @abstractmethod
    async def terminate_session(self, session_id: str) -> bool:
        """Terminate an existing session"""
        pass
    
    @abstractmethod
    async def send_input(self, session_id: str, input_text: str) -> bool:
        """Send input to a session"""
        pass
    
    @abstractmethod
    def get_session_status(self, session_id: str) -> Optional[str]:
        """Get session status"""
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup provider resources"""
        pass
    
    async def health_check(self) -> Dict[str, Any]:
        """Check provider health"""
        return {
            "provider_type": self.provider_type,
            "is_available": self.is_available,
            "status": "healthy" if self.is_available else "unhealthy"
        }


class TestBaseProvider:
    """Test suite for BaseProvider abstract class"""
    
    def test_provider_instantiation(self):
        """Test provider can be instantiated with correct parameters"""
        class TestProvider(BaseProvider):
            async def initialize(self): pass
            async def create_session(self, query: str, **kwargs): return {}
            async def terminate_session(self, session_id: str): return True
            async def send_input(self, session_id: str, input_text: str): return True
            def get_session_status(self, session_id: str): return "active"
            async def cleanup(self): pass
        
        provider = TestProvider("test", config_key="test_value")
        
        assert provider.provider_type == "test"
        assert provider.config == {"config_key": "test_value"}
        assert provider.is_available is False
    
    def test_provider_abstract_methods(self):
        """Test that abstract methods must be implemented"""
        with pytest.raises(TypeError):
            BaseProvider("test")
    
    @pytest.mark.asyncio
    async def test_health_check_default(self):
        """Test default health check implementation"""
        class TestProvider(BaseProvider):
            async def initialize(self): pass
            async def create_session(self, query: str, **kwargs): return {}
            async def terminate_session(self, session_id: str): return True
            async def send_input(self, session_id: str, input_text: str): return True
            def get_session_status(self, session_id: str): return "active"
            async def cleanup(self): pass
        
        provider = TestProvider("test")
        health = await provider.health_check()
        
        assert health["provider_type"] == "test"
        assert health["is_available"] is False
        assert health["status"] == "unhealthy"
    
    @pytest.mark.asyncio
    async def test_health_check_available(self):
        """Test health check when provider is available"""
        class TestProvider(BaseProvider):
            async def initialize(self): 
                self.is_available = True
            async def create_session(self, query: str, **kwargs): return {}
            async def terminate_session(self, session_id: str): return True
            async def send_input(self, session_id: str, input_text: str): return True
            def get_session_status(self, session_id: str): return "active"
            async def cleanup(self): pass
        
        provider = TestProvider("test")
        await provider.initialize()
        health = await provider.health_check()
        
        assert health["is_available"] is True
        assert health["status"] == "healthy"


class TestProviderContract:
    """Test the provider contract requirements"""
    
    @pytest.mark.asyncio
    async def test_provider_lifecycle(self):
        """Test complete provider lifecycle"""
        class TestProvider(BaseProvider):
            def __init__(self, provider_type: str, **config):
                super().__init__(provider_type, **config)
                self.sessions = {}
            
            async def initialize(self):
                self.is_available = True
            
            async def create_session(self, query: str, **kwargs):
                session_id = str(uuid.uuid4())
                self.sessions[session_id] = {
                    "id": session_id,
                    "status": "active",
                    "query": query
                }
                return self.sessions[session_id]
            
            async def terminate_session(self, session_id: str):
                if session_id in self.sessions:
                    self.sessions[session_id]["status"] = "terminated"
                    return True
                return False
            
            async def send_input(self, session_id: str, input_text: str):
                if session_id in self.sessions:
                    return True
                return False
            
            def get_session_status(self, session_id: str):
                if session_id in self.sessions:
                    return self.sessions[session_id]["status"]
                return None
            
            async def cleanup(self):
                self.sessions.clear()
                self.is_available = False
        
        # Test lifecycle
        provider = TestProvider("contract_test")
        
        # Initialize
        await provider.initialize()
        assert provider.is_available is True
        
        # Create session
        session = await provider.create_session("Test query")
        session_id = session["id"]
        assert session["status"] == "active"
        assert session["query"] == "Test query"
        
        # Check status
        status = provider.get_session_status(session_id)
        assert status == "active"
        
        # Send input
        result = await provider.send_input(session_id, "test input")
        assert result is True
        
        # Terminate session
        terminated = await provider.terminate_session(session_id)
        assert terminated is True
        assert provider.get_session_status(session_id) == "terminated"
        
        # Cleanup
        await provider.cleanup()
        assert provider.is_available is False
        assert len(provider.sessions) == 0
    
    @pytest.mark.asyncio
    async def test_provider_error_handling(self):
        """Test provider error handling"""
        class ErrorProvider(BaseProvider):
            async def initialize(self):
                raise RuntimeError("Initialization failed")
            
            async def create_session(self, query: str, **kwargs):
                raise ValueError("Session creation failed")
            
            async def terminate_session(self, session_id: str):
                raise ConnectionError("Termination failed")
            
            async def send_input(self, session_id: str, input_text: str):
                raise TimeoutError("Input timeout")
            
            def get_session_status(self, session_id: str):
                raise KeyError("Session not found")
            
            async def cleanup(self):
                raise Exception("Cleanup failed")
        
        provider = ErrorProvider("error_test")
        
        # Test initialization error
        with pytest.raises(RuntimeError):
            await provider.initialize()
        
        # Test session creation error
        with pytest.raises(ValueError):
            await provider.create_session("test")
        
        # Test termination error
        with pytest.raises(ConnectionError):
            await provider.terminate_session("test-id")
        
        # Test input error
        with pytest.raises(TimeoutError):
            await provider.send_input("test-id", "input")
        
        # Test status error
        with pytest.raises(KeyError):
            provider.get_session_status("test-id")
        
        # Test cleanup error
        with pytest.raises(Exception):
            await provider.cleanup()
    
    def test_provider_configuration(self):
        """Test provider configuration handling"""
        class ConfigProvider(BaseProvider):
            async def initialize(self): pass
            async def create_session(self, query: str, **kwargs): return {}
            async def terminate_session(self, session_id: str): return True
            async def send_input(self, session_id: str, input_text: str): return True
            def get_session_status(self, session_id: str): return "active"
            async def cleanup(self): pass
        
        # Test with various configurations
        configs = [
            {},
            {"timeout": 30},
            {"max_sessions": 10, "retry_count": 3},
            {"api_key": "test-key", "endpoint": "https://api.test.com"}
        ]
        
        for config in configs:
            provider = ConfigProvider("config_test", **config)
            assert provider.config == config
    
    @pytest.mark.asyncio
    async def test_concurrent_session_management(self):
        """Test concurrent session handling"""
        import asyncio
        
        class ConcurrentProvider(BaseProvider):
            def __init__(self, provider_type: str, **config):
                super().__init__(provider_type, **config)
                self.sessions = {}
                self.session_lock = asyncio.Lock()
            
            async def initialize(self):
                self.is_available = True
            
            async def create_session(self, query: str, **kwargs):
                async with self.session_lock:
                    session_id = str(uuid.uuid4())
                    self.sessions[session_id] = {
                        "id": session_id,
                        "status": "active",
                        "query": query
                    }
                    return self.sessions[session_id]
            
            async def terminate_session(self, session_id: str):
                async with self.session_lock:
                    if session_id in self.sessions:
                        del self.sessions[session_id]
                        return True
                    return False
            
            async def send_input(self, session_id: str, input_text: str):
                return session_id in self.sessions
            
            def get_session_status(self, session_id: str):
                return self.sessions.get(session_id, {}).get("status")
            
            async def cleanup(self):
                async with self.session_lock:
                    self.sessions.clear()
        
        provider = ConcurrentProvider("concurrent_test")
        await provider.initialize()
        
        # Create multiple sessions concurrently
        tasks = []
        for i in range(10):
            task = asyncio.create_task(
                provider.create_session(f"Query {i}")
            )
            tasks.append(task)
        
        sessions = await asyncio.gather(*tasks)
        assert len(sessions) == 10
        assert len(provider.sessions) == 10
        
        # Terminate sessions concurrently
        terminate_tasks = []
        for session in sessions:
            task = asyncio.create_task(
                provider.terminate_session(session["id"])
            )
            terminate_tasks.append(task)
        
        results = await asyncio.gather(*terminate_tasks)
        assert all(results)
        assert len(provider.sessions) == 0