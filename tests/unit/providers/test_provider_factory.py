"""
Unit tests for provider factory and dependency injection system
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from typing import Dict, Any, Type, Optional
from abc import ABC, abstractmethod
import uuid


# Mock provider interfaces for testing
class BaseProvider(ABC):
    """Abstract base provider"""
    
    def __init__(self, provider_type: str, **config):
        self.provider_type = provider_type
        self.config = config
        self.is_available = False
    
    @abstractmethod
    async def initialize(self) -> None:
        pass
    
    @abstractmethod
    async def create_session(self, query: str, **kwargs) -> Dict[str, Any]:
        pass


class MockClaudeProvider(BaseProvider):
    """Mock Claude Code provider"""
    
    async def initialize(self) -> None:
        self.is_available = True
    
    async def create_session(self, query: str, **kwargs) -> Dict[str, Any]:
        return {
            "session_id": str(uuid.uuid4()),
            "provider": "claude_code",
            "status": "active"
        }


class MockOpenCodeProvider(BaseProvider):
    """Mock OpenCode provider"""
    
    async def initialize(self) -> None:
        self.is_available = True
    
    async def create_session(self, query: str, **kwargs) -> Dict[str, Any]:
        return {
            "session_id": str(uuid.uuid4()),
            "provider": "opencode", 
            "status": "active"
        }


class ProviderFactory:
    """Factory class for creating and managing providers"""
    
    def __init__(self):
        self._providers: Dict[str, Type[BaseProvider]] = {}
        self._instances: Dict[str, BaseProvider] = {}
        self._default_provider: Optional[str] = None
    
    def register_provider(self, provider_type: str, provider_class: Type[BaseProvider]) -> None:
        """Register a provider type"""
        self._providers[provider_type] = provider_class
    
    def set_default_provider(self, provider_type: str) -> None:
        """Set the default provider type"""
        if provider_type not in self._providers:
            raise ValueError(f"Provider type '{provider_type}' not registered")
        self._default_provider = provider_type
    
    async def create_provider(self, provider_type: Optional[str] = None, **config) -> BaseProvider:
        """Create a provider instance"""
        if provider_type is None:
            if self._default_provider is None:
                raise ValueError("No default provider set and no provider type specified")
            provider_type = self._default_provider
        
        if provider_type not in self._providers:
            raise ValueError(f"Unknown provider type: {provider_type}")
        
        provider_class = self._providers[provider_type]
        instance = provider_class(provider_type, **config)
        
        await instance.initialize()
        self._instances[instance.provider_type] = instance
        
        return instance
    
    def get_provider(self, provider_type: str) -> Optional[BaseProvider]:
        """Get an existing provider instance"""
        return self._instances.get(provider_type)
    
    def get_available_providers(self) -> Dict[str, BaseProvider]:
        """Get all available (initialized) providers"""
        return {k: v for k, v in self._instances.items() if v.is_available}
    
    def get_registered_types(self) -> list[str]:
        """Get list of registered provider types"""
        return list(self._providers.keys())
    
    async def cleanup_all(self) -> None:
        """Cleanup all provider instances"""
        for provider in self._instances.values():
            if hasattr(provider, 'cleanup'):
                await provider.cleanup()
        self._instances.clear()


class ModelSelector:
    """Model selection and routing logic"""
    
    def __init__(self, factory: ProviderFactory):
        self.factory = factory
        self.selection_strategy = "availability"  # availability, performance, cost
        self.model_preferences = {
            "code_generation": ["claude_code", "opencode"],
            "text_analysis": ["opencode", "claude_code"],
            "debugging": ["claude_code"],
            "documentation": ["opencode", "claude_code"]
        }
    
    async def select_provider(self, task_type: str = "general", **kwargs) -> BaseProvider:
        """Select the best provider for a given task"""
        available_providers = self.factory.get_available_providers()
        
        if not available_providers:
            raise RuntimeError("No providers available")
        
        # Get preferred providers for task type
        preferred = self.model_preferences.get(task_type, [])
        
        # Find the first available preferred provider
        for provider_type in preferred:
            if provider_type in available_providers:
                return available_providers[provider_type]
        
        # Fallback to first available provider
        return list(available_providers.values())[0]
    
    def set_selection_strategy(self, strategy: str) -> None:
        """Set provider selection strategy"""
        valid_strategies = ["availability", "performance", "cost", "round_robin"]
        if strategy not in valid_strategies:
            raise ValueError(f"Invalid strategy. Must be one of: {valid_strategies}")
        self.selection_strategy = strategy
    
    def update_preferences(self, task_type: str, provider_order: list[str]) -> None:
        """Update provider preferences for a task type"""
        self.model_preferences[task_type] = provider_order


class TestProviderFactory:
    """Test suite for ProviderFactory"""
    
    @pytest.fixture
    def factory(self):
        """Create factory instance for testing"""
        factory = ProviderFactory()
        factory.register_provider("claude_code", MockClaudeProvider)
        factory.register_provider("opencode", MockOpenCodeProvider)
        return factory
    
    def test_register_provider(self, factory):
        """Test provider registration"""
        # Test registration
        class TestProvider(BaseProvider):
            async def initialize(self): pass
            async def create_session(self, query: str, **kwargs): return {}
        
        factory.register_provider("test_provider", TestProvider)
        
        assert "test_provider" in factory.get_registered_types()
        assert "claude_code" in factory.get_registered_types()
        assert "opencode" in factory.get_registered_types()
    
    def test_set_default_provider(self, factory):
        """Test setting default provider"""
        factory.set_default_provider("claude_code")
        assert factory._default_provider == "claude_code"
        
        # Test setting unknown provider
        with pytest.raises(ValueError, match="Provider type 'unknown' not registered"):
            factory.set_default_provider("unknown")
    
    @pytest.mark.asyncio
    async def test_create_provider_explicit_type(self, factory):
        """Test creating provider with explicit type"""
        provider = await factory.create_provider("claude_code", config_key="test_value")
        
        assert provider.provider_type == "claude_code"
        assert provider.config["config_key"] == "test_value"
        assert provider.is_available is True
    
    @pytest.mark.asyncio
    async def test_create_provider_default_type(self, factory):
        """Test creating provider with default type"""
        factory.set_default_provider("opencode")
        
        provider = await factory.create_provider()
        
        assert provider.provider_type == "opencode"
        assert provider.is_available is True
    
    @pytest.mark.asyncio
    async def test_create_provider_no_default(self, factory):
        """Test creating provider without default set"""
        with pytest.raises(ValueError, match="No default provider set"):
            await factory.create_provider()
    
    @pytest.mark.asyncio
    async def test_create_provider_unknown_type(self, factory):
        """Test creating unknown provider type"""
        with pytest.raises(ValueError, match="Unknown provider type: unknown"):
            await factory.create_provider("unknown")
    
    @pytest.mark.asyncio
    async def test_get_provider(self, factory):
        """Test getting existing provider instance"""
        # Create provider first
        await factory.create_provider("claude_code")
        
        # Get existing provider
        provider = factory.get_provider("claude_code")
        assert provider is not None
        assert provider.provider_type == "claude_code"
        
        # Get non-existent provider
        provider = factory.get_provider("nonexistent")
        assert provider is None
    
    @pytest.mark.asyncio
    async def test_get_available_providers(self, factory):
        """Test getting available providers"""
        # Initially no providers
        available = factory.get_available_providers()
        assert len(available) == 0
        
        # Create providers
        await factory.create_provider("claude_code")
        await factory.create_provider("opencode")
        
        available = factory.get_available_providers()
        assert len(available) == 2
        assert "claude_code" in available
        assert "opencode" in available
        
        # All should be available
        for provider in available.values():
            assert provider.is_available is True
    
    def test_get_registered_types(self, factory):
        """Test getting registered provider types"""
        types = factory.get_registered_types()
        assert "claude_code" in types
        assert "opencode" in types
        assert len(types) == 2
    
    @pytest.mark.asyncio
    async def test_cleanup_all(self, factory):
        """Test cleanup of all providers"""
        # Create providers with mock cleanup methods
        provider1 = await factory.create_provider("claude_code")
        provider2 = await factory.create_provider("opencode")
        
        provider1.cleanup = AsyncMock()
        provider2.cleanup = AsyncMock()
        
        assert len(factory._instances) == 2
        
        await factory.cleanup_all()
        
        assert len(factory._instances) == 0
        provider1.cleanup.assert_called_once()
        provider2.cleanup.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_multiple_instances_same_type(self, factory):
        """Test creating multiple instances of same provider type"""
        provider1 = await factory.create_provider("claude_code", session_id="session1")
        provider2 = await factory.create_provider("claude_code", session_id="session2")
        
        # Second instance should replace the first in factory
        assert factory.get_provider("claude_code") is provider2
        assert provider1.config["session_id"] == "session1"
        assert provider2.config["session_id"] == "session2"


class TestModelSelector:
    """Test suite for ModelSelector"""
    
    @pytest.fixture
    async def selector_with_providers(self):
        """Create selector with initialized providers"""
        factory = ProviderFactory()
        factory.register_provider("claude_code", MockClaudeProvider)
        factory.register_provider("opencode", MockOpenCodeProvider)
        
        # Create providers
        await factory.create_provider("claude_code")
        await factory.create_provider("opencode")
        
        selector = ModelSelector(factory)
        return selector, factory
    
    @pytest.mark.asyncio
    async def test_select_provider_by_task_type(self, selector_with_providers):
        """Test provider selection by task type"""
        selector, factory = selector_with_providers
        
        # Test code generation (prefers claude_code)
        provider = await selector.select_provider("code_generation")
        assert provider.provider_type == "claude_code"
        
        # Test text analysis (prefers opencode)
        provider = await selector.select_provider("text_analysis")
        assert provider.provider_type == "opencode"
        
        # Test debugging (only claude_code)
        provider = await selector.select_provider("debugging")
        assert provider.provider_type == "claude_code"
    
    @pytest.mark.asyncio
    async def test_select_provider_fallback(self, selector_with_providers):
        """Test fallback when preferred provider not available"""
        selector, factory = selector_with_providers
        
        # Remove claude_code provider
        factory._instances.pop("claude_code")
        
        # Should fallback to opencode for code_generation
        provider = await selector.select_provider("code_generation")
        assert provider.provider_type == "opencode"
    
    @pytest.mark.asyncio
    async def test_select_provider_no_providers(self):
        """Test selection when no providers available"""
        factory = ProviderFactory()
        selector = ModelSelector(factory)
        
        with pytest.raises(RuntimeError, match="No providers available"):
            await selector.select_provider()
    
    @pytest.mark.asyncio
    async def test_select_provider_unknown_task(self, selector_with_providers):
        """Test selection with unknown task type"""
        selector, factory = selector_with_providers
        
        # Unknown task should use first available provider
        provider = await selector.select_provider("unknown_task")
        assert provider is not None
        assert provider.provider_type in ["claude_code", "opencode"]
    
    def test_set_selection_strategy(self, selector_with_providers):
        """Test setting selection strategy"""
        selector, factory = selector_with_providers
        
        selector.set_selection_strategy("performance")
        assert selector.selection_strategy == "performance"
        
        selector.set_selection_strategy("cost")
        assert selector.selection_strategy == "cost"
        
        with pytest.raises(ValueError, match="Invalid strategy"):
            selector.set_selection_strategy("invalid")
    
    def test_update_preferences(self, selector_with_providers):
        """Test updating task preferences"""
        selector, factory = selector_with_providers
        
        original_prefs = selector.model_preferences["code_generation"].copy()
        
        # Update preferences
        new_order = ["opencode", "claude_code"]
        selector.update_preferences("code_generation", new_order)
        
        assert selector.model_preferences["code_generation"] == new_order
        assert selector.model_preferences["code_generation"] != original_prefs
    
    @pytest.mark.asyncio
    async def test_concurrent_provider_selection(self, selector_with_providers):
        """Test concurrent provider selection"""
        import asyncio
        
        selector, factory = selector_with_providers
        
        # Create multiple concurrent selections
        tasks = []
        for i in range(10):
            task_type = "code_generation" if i % 2 == 0 else "text_analysis"
            task = asyncio.create_task(selector.select_provider(task_type))
            tasks.append(task)
        
        providers = await asyncio.gather(*tasks)
        
        assert len(providers) == 10
        for provider in providers:
            assert provider.provider_type in ["claude_code", "opencode"]


class TestDependencyInjection:
    """Test dependency injection patterns"""
    
    @pytest.fixture
    def di_container(self):
        """Create a simple DI container for testing"""
        class DIContainer:
            def __init__(self):
                self._services = {}
                self._singletons = {}
            
            def register_singleton(self, service_type: type, instance: Any) -> None:
                self._singletons[service_type] = instance
            
            def register_transient(self, service_type: type, factory: callable) -> None:
                self._services[service_type] = factory
            
            def resolve(self, service_type: type) -> Any:
                # Check singletons first
                if service_type in self._singletons:
                    return self._singletons[service_type]
                
                # Check transient services
                if service_type in self._services:
                    return self._services[service_type]()
                
                raise ValueError(f"Service {service_type} not registered")
        
        return DIContainer()
    
    @pytest.mark.asyncio
    async def test_singleton_provider_injection(self, di_container):
        """Test singleton provider injection"""
        factory = ProviderFactory()
        factory.register_provider("claude_code", MockClaudeProvider)
        
        # Register factory as singleton
        di_container.register_singleton(ProviderFactory, factory)
        
        # Resolve should return same instance
        resolved1 = di_container.resolve(ProviderFactory)
        resolved2 = di_container.resolve(ProviderFactory)
        
        assert resolved1 is resolved2
        assert resolved1 is factory
    
    def test_transient_selector_injection(self, di_container):
        """Test transient selector injection"""
        factory = ProviderFactory()
        
        # Register selector factory
        def create_selector():
            return ModelSelector(factory)
        
        di_container.register_transient(ModelSelector, create_selector)
        
        # Resolve should create new instances
        selector1 = di_container.resolve(ModelSelector)
        selector2 = di_container.resolve(ModelSelector)
        
        assert selector1 is not selector2
        assert isinstance(selector1, ModelSelector)
        assert isinstance(selector2, ModelSelector)
    
    def test_service_not_registered(self, di_container):
        """Test resolving unregistered service"""
        with pytest.raises(ValueError, match="Service .* not registered"):
            di_container.resolve(str)
    
    @pytest.mark.asyncio
    async def test_complex_dependency_chain(self, di_container):
        """Test complex dependency injection chain"""
        # Create services
        factory = ProviderFactory()
        factory.register_provider("claude_code", MockClaudeProvider)
        
        def create_selector():
            return ModelSelector(factory)
        
        class SessionService:
            def __init__(self, selector: ModelSelector):
                self.selector = selector
        
        def create_session_service():
            selector = di_container.resolve(ModelSelector)
            return SessionService(selector)
        
        # Register services
        di_container.register_singleton(ProviderFactory, factory)
        di_container.register_transient(ModelSelector, create_selector)
        di_container.register_transient(SessionService, create_session_service)
        
        # Resolve session service
        session_service = di_container.resolve(SessionService)
        
        assert isinstance(session_service, SessionService)
        assert isinstance(session_service.selector, ModelSelector)
        assert session_service.selector.factory is factory