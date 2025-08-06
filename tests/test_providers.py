"""
Provider System Tests

Comprehensive tests for the provider abstraction layer.
Tests base interfaces, provider implementations, factory, and integration.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.jelmore.providers import (
    BaseProvider,
    BaseSession,
    ProviderFactory,
    get_provider_factory,
    ClaudeProvider,
    OpenCodeProvider,
    SessionConfig,
    SessionStatus,
    StreamEventType,
    StreamResponse,
    ProviderError,
    SessionError,
    ModelNotSupportedError
)
from src.jelmore.providers.config import (
    ProviderSystemConfig,
    load_provider_config,
    get_provider_config_dict
)


class TestProviderSystemConfig:
    """Test provider configuration system"""
    
    def test_default_config(self):
        """Test default configuration values"""
        config = ProviderSystemConfig()
        
        assert config.default_provider == "claude"
        assert config.auto_selection is True
        assert config.load_balancing is True
        assert config.cost_optimization is False
        assert config.claude.enabled is True
        assert config.claude.default_model == "claude-3-5-sonnet-20241022"
        assert config.opencode.enabled is True
        assert config.opencode.default_model == "deepseek-v3"
    
    def test_config_validation(self):
        """Test configuration validation"""
        # Valid config
        config = ProviderSystemConfig(default_provider="claude")
        assert config.default_provider == "claude"
        
        # Invalid default provider
        with pytest.raises(ValueError, match="Default provider must be one of"):
            ProviderSystemConfig(default_provider="invalid")
    
    @patch.dict("os.environ", {
        "JELMORE_DEFAULT_PROVIDER": "opencode",
        "JELMORE_CLAUDE_BIN": "/custom/claude",
        "JELMORE_OPENCODE_API_ENDPOINT": "http://custom:8080"
    })
    def test_load_config_from_env(self):
        """Test loading configuration from environment variables"""
        config = load_provider_config()
        
        assert config.default_provider == "opencode"
        assert config.claude.claude_bin == "/custom/claude"
        assert config.opencode.api_endpoint == "http://custom:8080"
    
    def test_get_provider_config_dict(self):
        """Test conversion to provider config dictionary"""
        config = ProviderSystemConfig()
        config_dict = get_provider_config_dict(config)
        
        assert "providers" in config_dict
        assert "claude" in config_dict["providers"]
        assert "opencode" in config_dict["providers"]
        assert config_dict["default_provider"] == "claude"
        assert config_dict["load_balancing"] is True


class TestBaseInterfaces:
    """Test base provider and session interfaces"""
    
    def test_session_config_creation(self):
        """Test SessionConfig creation and validation"""
        config = SessionConfig(
            model="test-model",
            max_turns=5,
            temperature=0.8,
            working_directory=Path("/tmp")
        )
        
        assert config.model == "test-model"
        assert config.max_turns == 5
        assert config.temperature == 0.8
        assert config.working_directory == Path("/tmp")
    
    def test_stream_response_creation(self):
        """Test StreamResponse creation"""
        response = StreamResponse(
            event_type=StreamEventType.ASSISTANT,
            content="Hello world",
            metadata={"test": True},
            session_id="test-session"
        )
        
        assert response.event_type == StreamEventType.ASSISTANT
        assert response.content == "Hello world"
        assert response.metadata["test"] is True
        assert response.session_id == "test-session"
    
    def test_provider_error_hierarchy(self):
        """Test error hierarchy"""
        # Base provider error
        error = ProviderError("Test error", "test-provider", "session-123")
        assert str(error) == "Test error"
        assert error.provider == "test-provider"
        assert error.session_id == "session-123"
        
        # Session error inherits from provider error
        session_error = SessionError("Session failed", "test-provider", "session-456")
        assert isinstance(session_error, ProviderError)
        assert session_error.session_id == "session-456"
        
        # Model not supported error
        model_error = ModelNotSupportedError("Model not found", "test-provider")
        assert isinstance(model_error, ProviderError)


@pytest.fixture
async def claude_provider():
    """Create a Claude provider for testing"""
    config = {
        "claude_bin": "echo",  # Use echo command for testing
        "default_model": "claude-3-5-sonnet-20241022",
        "max_concurrent_sessions": 2
    }
    provider = ClaudeProvider(config)
    yield provider
    # Cleanup
    for session_id in list(provider.sessions.keys()):
        await provider.terminate_session(session_id)


@pytest.fixture
async def opencode_provider():
    """Create an OpenCode provider for testing"""
    config = {
        "opencode_bin": "echo",
        "api_endpoint": "http://localhost:8080",
        "default_model": "deepseek-v3",
        "max_concurrent_sessions": 3
    }
    provider = OpenCodeProvider(config)
    yield provider
    # Cleanup
    for session_id in list(provider.sessions.keys()):
        await provider.terminate_session(session_id)


class TestClaudeProvider:
    """Test Claude provider implementation"""
    
    @pytest.mark.asyncio
    async def test_provider_creation(self, claude_provider):
        """Test Claude provider creation"""
        assert claude_provider.name == "claude"
        assert len(claude_provider.available_models) > 0
        assert claude_provider.capabilities.supports_streaming is True
        assert claude_provider.capabilities.supports_tools is True
        assert claude_provider.capabilities.max_concurrent_sessions == 2
    
    @pytest.mark.asyncio
    async def test_health_check(self, claude_provider):
        """Test provider health check"""
        health = await claude_provider.health_check()
        assert "status" in health
        assert "provider" in health
        assert health["provider"] == "claude"
    
    @pytest.mark.asyncio
    async def test_model_info(self, claude_provider):
        """Test model information retrieval"""
        model_info = claude_provider.get_model_info("claude-3-5-sonnet-20241022")
        assert model_info is not None
        assert model_info.name == "claude-3-5-sonnet-20241022"
        assert model_info.supports_streaming is True
        assert model_info.supports_tools is True
        
        # Test non-existent model
        assert claude_provider.get_model_info("non-existent") is None
    
    @pytest.mark.asyncio
    async def test_session_creation(self, claude_provider):
        """Test session creation"""
        config = SessionConfig(model="claude-3-5-sonnet-20241022")
        
        # Mock the subprocess creation to avoid actual Claude Code execution
        with patch('asyncio.create_subprocess_exec') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.stdout = AsyncMock()
            mock_process.stdin = AsyncMock()
            mock_process.stderr = AsyncMock()
            mock_subprocess.return_value = mock_process
            
            session = await claude_provider.create_session("Test query", config)
            
            assert session.session_id is not None
            assert session.config.model == "claude-3-5-sonnet-20241022"
            assert len(claude_provider.sessions) == 1
    
    @pytest.mark.asyncio
    async def test_session_limit(self, claude_provider):
        """Test session concurrency limits"""
        config = SessionConfig(model="claude-3-5-sonnet-20241022")
        
        with patch('asyncio.create_subprocess_exec') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.stdout = AsyncMock()
            mock_process.stdin = AsyncMock() 
            mock_process.stderr = AsyncMock()
            mock_subprocess.return_value = mock_process
            
            # Create max sessions
            sessions = []
            for i in range(2):  # max_concurrent_sessions = 2
                session = await claude_provider.create_session(f"Query {i}", config)
                sessions.append(session)
            
            # Try to create one more - should fail
            with pytest.raises(ProviderError, match="Maximum concurrent sessions reached"):
                await claude_provider.create_session("Overflow query", config)
    
    @pytest.mark.asyncio
    async def test_unsupported_model(self, claude_provider):
        """Test unsupported model handling"""
        config = SessionConfig(model="unsupported-model")
        
        with pytest.raises(ProviderError, match="Model unsupported-model not supported"):
            await claude_provider.create_session("Test query", config)
    
    @pytest.mark.asyncio
    async def test_session_termination(self, claude_provider):
        """Test session termination"""
        config = SessionConfig(model="claude-3-5-sonnet-20241022")
        
        with patch('asyncio.create_subprocess_exec') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.stdout = AsyncMock()
            mock_process.stdin = AsyncMock()
            mock_process.stderr = AsyncMock()
            mock_subprocess.return_value = mock_process
            
            session = await claude_provider.create_session("Test query", config)
            session_id = session.session_id
            
            # Terminate session
            result = await claude_provider.terminate_session(session_id)
            assert result is True
            assert len(claude_provider.sessions) == 0
            
            # Try to terminate non-existent session
            result = await claude_provider.terminate_session("non-existent")
            assert result is False


class TestOpenCodeProvider:
    """Test OpenCode provider implementation"""
    
    @pytest.mark.asyncio
    async def test_provider_creation(self, opencode_provider):
        """Test OpenCode provider creation"""
        assert opencode_provider.name == "opencode"
        assert len(opencode_provider.available_models) > 0
        assert opencode_provider.capabilities.supports_streaming is True
        assert opencode_provider.capabilities.supports_tools is False  # OpenCode doesn't support tools
        assert opencode_provider.capabilities.max_concurrent_sessions == 3
    
    @pytest.mark.asyncio
    async def test_available_models(self, opencode_provider):
        """Test available models"""
        models = opencode_provider.available_models
        model_names = [m.name for m in models]
        
        assert "deepseek-v3" in model_names
        assert "kimi-k2" in model_names
        assert "qwen2.5-coder" in model_names
        
        # Test model with long context
        kimi_model = opencode_provider.get_model_info("kimi-k2")
        assert kimi_model.context_length == 2000000  # 2M tokens
    
    @pytest.mark.asyncio
    async def test_session_creation(self, opencode_provider):
        """Test session creation"""
        config = SessionConfig(model="deepseek-v3")
        session = await opencode_provider.create_session("Test query", config)
        
        assert session.session_id is not None
        assert session.config.model == "deepseek-v3"
        assert len(opencode_provider.sessions) == 1
    
    @pytest.mark.asyncio
    async def test_session_messaging(self, opencode_provider):
        """Test session messaging"""
        config = SessionConfig(model="deepseek-v3")
        session = await opencode_provider.create_session("Initial query", config)
        
        # Send follow-up message
        await session.send_message("Follow-up question")
        
        # Check conversation history (internal)
        assert len(session._conversation_history) >= 2  # System + user messages
    
    @pytest.mark.asyncio
    async def test_health_check(self, opencode_provider):
        """Test provider health check"""
        health = await opencode_provider.health_check()
        assert health["status"] == "healthy"
        assert health["provider"] == "opencode"
        assert "available_models" in health


class TestProviderFactory:
    """Test provider factory functionality"""
    
    @pytest.mark.asyncio
    async def test_factory_creation(self):
        """Test factory creation and provider registration"""
        factory = ProviderFactory()
        
        # Check built-in providers are registered
        available = factory.list_available_providers()
        assert "claude" in available
        assert "opencode" in available
    
    @pytest.mark.asyncio
    async def test_provider_configuration(self):
        """Test provider configuration"""
        factory = ProviderFactory()
        
        # Configure providers
        claude_config = {"claude_bin": "claude", "max_concurrent_sessions": 5}
        opencode_config = {"api_endpoint": "http://localhost:8080"}
        
        factory.configure_provider("claude", claude_config)
        factory.configure_provider("opencode", opencode_config)
        
        assert "claude" in factory.list_configured_providers()
        assert "opencode" in factory.list_configured_providers()
    
    @pytest.mark.asyncio
    async def test_provider_creation_and_retrieval(self):
        """Test creating and retrieving providers"""
        factory = ProviderFactory()
        
        config = {
            "opencode_bin": "echo",
            "api_endpoint": "http://localhost:8080",
            "default_model": "deepseek-v3"
        }
        
        # Create provider
        provider = await factory.create_provider("opencode", config)
        assert provider.name == "opencode"
        
        # Retrieve provider
        retrieved = await factory.get_provider("opencode")
        assert retrieved is provider
        
        # Get non-existent provider
        missing = await factory.get_provider("missing")
        assert missing is None
        
        # Cleanup
        await factory.shutdown_provider("opencode")
    
    @pytest.mark.asyncio
    async def test_default_provider(self):
        """Test default provider functionality"""
        factory = ProviderFactory()
        
        # Set default
        factory.set_default_provider("opencode")
        
        # Create the provider so we can get it
        config = {"opencode_bin": "echo", "default_model": "deepseek-v3"}
        await factory.create_provider("opencode", config)
        
        # Get default
        default = await factory.get_default_provider()
        assert default is not None
        assert default.name == "opencode"
        
        # Cleanup
        await factory.shutdown_all_providers()
    
    @pytest.mark.asyncio
    async def test_provider_selection(self):
        """Test automatic provider selection"""
        factory = ProviderFactory()
        
        # Create both providers
        claude_config = {"claude_bin": "echo", "default_model": "claude-3-5-sonnet-20241022"}
        opencode_config = {"opencode_bin": "echo", "default_model": "deepseek-v3"}
        
        claude_provider = await factory.create_provider("claude", claude_config)
        opencode_provider = await factory.create_provider("opencode", opencode_config)
        
        # Test model-specific selection
        requirements = {"model": "claude-3-5-sonnet-20241022"}
        selected = await factory.select_best_provider(requirements)
        assert selected == "claude"
        
        requirements = {"model": "deepseek-v3"}
        selected = await factory.select_best_provider(requirements)
        assert selected == "opencode"
        
        # Test capability-based selection
        requirements = {"capabilities": ["supports_tools"]}
        selected = await factory.select_best_provider(requirements)
        assert selected == "claude"  # Claude supports tools, OpenCode doesn't
        
        # Cleanup
        await factory.shutdown_all_providers()
    
    @pytest.mark.asyncio
    async def test_health_checks(self):
        """Test health checking functionality"""
        factory = ProviderFactory()
        
        # Create providers
        config = {"opencode_bin": "echo", "default_model": "deepseek-v3"}
        await factory.create_provider("opencode", config)
        
        # Health check all
        health_results = await factory.health_check_all()
        assert "opencode" in health_results
        assert health_results["opencode"]["status"] == "healthy"
        
        # Cleanup
        await factory.shutdown_all_providers()
    
    @pytest.mark.asyncio
    async def test_metrics_collection(self):
        """Test metrics collection"""
        factory = ProviderFactory()
        
        # Create provider and session
        config = {"opencode_bin": "echo", "default_model": "deepseek-v3"}
        provider = await factory.create_provider("opencode", config)
        session = await provider.create_session("test query")
        
        # Get metrics
        metrics = await factory.get_provider_metrics()
        assert metrics["total_providers"] == 1
        assert "opencode" in metrics["providers"]
        
        provider_metrics = metrics["providers"]["opencode"]
        assert provider_metrics["total_sessions"] >= 1
        
        # Cleanup
        await factory.shutdown_all_providers()
    
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in factory"""
        factory = ProviderFactory()
        
        # Try to create unknown provider
        with pytest.raises(ProviderError, match="Unknown provider type"):
            await factory.create_provider("unknown")
        
        # Try to set invalid default
        with pytest.raises(ProviderError, match="Unknown provider type"):
            factory.set_default_provider("invalid")


class TestIntegration:
    """Test integration scenarios"""
    
    @pytest.mark.asyncio
    async def test_multi_provider_workflow(self):
        """Test workflow with multiple providers"""
        factory = ProviderFactory()
        
        # Configure multiple providers
        claude_config = {"claude_bin": "echo", "max_concurrent_sessions": 1}
        opencode_config = {"opencode_bin": "echo", "max_concurrent_sessions": 2}
        
        claude_provider = await factory.create_provider("claude", claude_config)
        opencode_provider = await factory.create_provider("opencode", opencode_config)
        
        # Create sessions with different models
        claude_session = await claude_provider.create_session(
            "Claude query",
            SessionConfig(model="claude-3-5-sonnet-20241022")
        )
        
        opencode_session = await opencode_provider.create_session(
            "OpenCode query", 
            SessionConfig(model="deepseek-v3")
        )
        
        # Verify sessions are in different providers
        assert claude_session.session_id in claude_provider.sessions
        assert opencode_session.session_id in opencode_provider.sessions
        assert claude_session.session_id not in opencode_provider.sessions
        assert opencode_session.session_id not in claude_provider.sessions
        
        # List all sessions
        claude_sessions = await claude_provider.list_sessions()
        opencode_sessions = await opencode_provider.list_sessions()
        
        assert len(claude_sessions) == 1
        assert len(opencode_sessions) == 1
        
        # Cleanup
        await factory.shutdown_all_providers()
    
    @pytest.mark.asyncio
    async def test_session_lifecycle(self):
        """Test complete session lifecycle"""
        factory = ProviderFactory()
        
        # Create provider
        config = {"opencode_bin": "echo", "default_model": "deepseek-v3"}
        provider = await factory.create_provider("opencode", config)
        
        # Create session
        session = await provider.create_session("Initial query")
        initial_status = await session.get_status()
        assert initial_status["status"] in ["active", "idle"]
        
        # Send message
        await session.send_message("Follow-up message")
        
        # Suspend session
        state = await session.suspend()
        assert "session_id" in state
        assert "conversation_history" in state
        
        suspended_status = await session.get_status()
        assert suspended_status["status"] == "suspended"
        
        # Resume session
        await session.resume(state)
        resumed_status = await session.get_status()
        assert resumed_status["status"] in ["idle", "active"]
        
        # Terminate session
        await session.terminate()
        final_status = await session.get_status()
        assert final_status["status"] == "terminated"
        
        # Cleanup
        await factory.shutdown_all_providers()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])