"""
Provider Factory with Dependency Injection

Factory pattern for creating and managing AI providers.
Supports runtime provider selection, configuration, and lifecycle management.
"""

import asyncio
from typing import Any, Dict, List, Optional, Type
from functools import lru_cache
import structlog

from .base import BaseProvider, SessionConfig, ProviderError
from .claude import ClaudeProvider
from .opencode import OpenCodeProvider

logger = structlog.get_logger()


class ProviderFactory:
    """Factory for creating and managing AI providers"""
    
    def __init__(self):
        self._providers: Dict[str, BaseProvider] = {}
        self._provider_configs: Dict[str, Dict[str, Any]] = {}
        self._default_provider: Optional[str] = None
        
        # Register built-in providers
        self._provider_classes: Dict[str, Type[BaseProvider]] = {
            "claude": ClaudeProvider,
            "opencode": OpenCodeProvider,
        }
    
    def register_provider(self, name: str, provider_class: Type[BaseProvider]) -> None:
        """Register a new provider type"""
        self._provider_classes[name] = provider_class
        logger.info(f"Registered provider type: {name}")
    
    def configure_provider(self, name: str, config: Dict[str, Any]) -> None:
        """Configure a provider without creating an instance"""
        self._provider_configs[name] = config.copy()
        logger.info(f"Configured provider: {name}")
    
    async def create_provider(self, name: str, config: Optional[Dict[str, Any]] = None) -> BaseProvider:
        """Create a provider instance"""
        if name not in self._provider_classes:
            raise ProviderError(f"Unknown provider type: {name}", name)
        
        # Use provided config or stored config
        provider_config = config or self._provider_configs.get(name, {})
        
        try:
            provider_class = self._provider_classes[name]
            provider = provider_class(provider_config)
            
            # Store the provider instance
            self._providers[name] = provider
            
            # Perform health check
            health_status = await provider.health_check()
            if health_status.get("status") != "healthy":
                logger.warning(f"Provider {name} is not healthy", status=health_status)
            
            logger.info(f"Created provider: {name}", config_keys=list(provider_config.keys()))
            return provider
            
        except Exception as e:
            logger.error(f"Failed to create provider {name}", error=str(e))
            raise ProviderError(f"Failed to create provider {name}: {e}", name)
    
    async def get_provider(self, name: str) -> Optional[BaseProvider]:
        """Get an existing provider instance"""
        if name in self._providers:
            return self._providers[name]
        
        # Try to create if configuration exists
        if name in self._provider_configs:
            return await self.create_provider(name)
        
        return None
    
    async def get_or_create_provider(self, name: str, config: Optional[Dict[str, Any]] = None) -> BaseProvider:
        """Get existing provider or create if it doesn't exist"""
        provider = await self.get_provider(name)
        if provider is None:
            provider = await self.create_provider(name, config)
        return provider
    
    def set_default_provider(self, name: str) -> None:
        """Set the default provider"""
        if name not in self._provider_classes:
            raise ProviderError(f"Unknown provider type: {name}", name)
        self._default_provider = name
        logger.info(f"Set default provider: {name}")
    
    async def get_default_provider(self) -> Optional[BaseProvider]:
        """Get the default provider"""
        if self._default_provider:
            return await self.get_provider(self._default_provider)
        return None
    
    def list_available_providers(self) -> List[str]:
        """List all available provider types"""
        return list(self._provider_classes.keys())
    
    def list_configured_providers(self) -> List[str]:
        """List all configured providers"""
        return list(self._provider_configs.keys())
    
    def list_active_providers(self) -> List[str]:
        """List all active provider instances"""
        return list(self._providers.keys())
    
    async def shutdown_provider(self, name: str) -> bool:
        """Shutdown and remove a provider"""
        if name in self._providers:
            provider = self._providers[name]
            
            # Terminate all sessions
            sessions = await provider.list_sessions()
            for session_data in sessions:
                await provider.terminate_session(session_data["id"])
            
            del self._providers[name]
            logger.info(f"Shut down provider: {name}")
            return True
        return False
    
    async def shutdown_all_providers(self) -> None:
        """Shutdown all active providers"""
        for name in list(self._providers.keys()):
            await self.shutdown_provider(name)
        logger.info("All providers shut down")
    
    async def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """Perform health check on all active providers"""
        results = {}
        for name, provider in self._providers.items():
            try:
                results[name] = await provider.health_check()
            except Exception as e:
                results[name] = {
                    "status": "error",
                    "error": str(e)
                }
        return results
    
    async def get_provider_metrics(self) -> Dict[str, Any]:
        """Get metrics for all active providers"""
        metrics = {
            "total_providers": len(self._providers),
            "configured_providers": len(self._provider_configs),
            "available_types": len(self._provider_classes),
            "default_provider": self._default_provider,
            "providers": {}
        }
        
        for name, provider in self._providers.items():
            try:
                provider_metrics = await provider.get_metrics()
                metrics["providers"][name] = provider_metrics
            except Exception as e:
                metrics["providers"][name] = {
                    "status": "error",
                    "error": str(e)
                }
        
        return metrics
    
    async def select_best_provider(self, requirements: Dict[str, Any]) -> Optional[str]:
        """Select the best provider based on requirements"""
        # Requirements can include:
        # - model: specific model needed
        # - capabilities: list of required capabilities
        # - load_balancing: prefer less loaded providers
        # - cost_optimization: prefer cheaper providers
        
        best_provider = None
        best_score = -1
        
        for name, provider in self._providers.items():
            score = 0
            
            # Check if provider supports required model
            required_model = requirements.get("model")
            if required_model:
                if provider.supports_model(required_model):
                    score += 10
                else:
                    continue  # Skip if model not supported
            
            # Check capabilities
            required_capabilities = requirements.get("capabilities", [])
            for capability in required_capabilities:
                if hasattr(provider.capabilities, capability):
                    if getattr(provider.capabilities, capability):
                        score += 5
                    else:
                        score -= 10  # Penalize for missing required capability
            
            # Load balancing
            if requirements.get("load_balancing", False):
                session_count = len(provider.sessions)
                max_sessions = provider.capabilities.max_concurrent_sessions
                load_ratio = session_count / max_sessions if max_sessions > 0 else 1
                score -= int(load_ratio * 10)  # Lower score for higher load
            
            # Cost optimization (if model info has cost data)
            if requirements.get("cost_optimization", False) and required_model:
                model_info = provider.get_model_info(required_model)
                if model_info and model_info.cost_per_token:
                    # Lower cost = higher score (inverse relationship)
                    score += int(10 / model_info.cost_per_token)
            
            # Health status
            try:
                health = await provider.health_check()
                if health.get("status") == "healthy":
                    score += 5
                else:
                    score -= 20
            except Exception:
                score -= 30
            
            if score > best_score:
                best_score = score
                best_provider = name
        
        if best_provider:
            logger.info(f"Selected best provider: {best_provider}", 
                       score=best_score, 
                       requirements=requirements)
        else:
            logger.warning("No suitable provider found", requirements=requirements)
        
        return best_provider


# Global factory instance
_factory_instance: Optional[ProviderFactory] = None


@lru_cache(maxsize=1)
def get_provider_factory() -> ProviderFactory:
    """Get the global provider factory instance"""
    global _factory_instance
    if _factory_instance is None:
        _factory_instance = ProviderFactory()
    return _factory_instance


async def initialize_providers(config: Dict[str, Any]) -> ProviderFactory:
    """Initialize providers from configuration"""
    factory = get_provider_factory()
    
    # Configure providers from config
    providers_config = config.get("providers", {})
    
    for provider_name, provider_config in providers_config.items():
        factory.configure_provider(provider_name, provider_config)
        
        # Create provider if enabled
        if provider_config.get("enabled", True):
            try:
                await factory.create_provider(provider_name)
            except Exception as e:
                logger.error(f"Failed to initialize provider {provider_name}", error=str(e))
    
    # Set default provider
    default_provider = config.get("default_provider")
    if default_provider:
        factory.set_default_provider(default_provider)
    
    logger.info("Provider factory initialized", 
                active_providers=factory.list_active_providers(),
                default=default_provider)
    
    return factory


async def shutdown_providers() -> None:
    """Shutdown all providers"""
    factory = get_provider_factory()
    await factory.shutdown_all_providers()
    logger.info("All providers shut down")


# Convenience functions for dependency injection
async def create_session_with_auto_selection(
    query: str,
    requirements: Optional[Dict[str, Any]] = None,
    config: Optional[SessionConfig] = None
) -> Any:  # Returns BaseSession but avoiding circular import
    """Create a session with automatic provider selection"""
    factory = get_provider_factory()
    
    # Select best provider
    provider_name = await factory.select_best_provider(requirements or {})
    if not provider_name:
        # Fallback to default provider
        default_provider = await factory.get_default_provider()
        if default_provider:
            provider = default_provider
        else:
            raise ProviderError("No suitable provider available", "factory")
    else:
        provider = await factory.get_provider(provider_name)
        if not provider:
            raise ProviderError(f"Provider {provider_name} not available", provider_name)
    
    # Create session
    session = await provider.create_session(query, config)
    logger.info(f"Created auto-selected session", 
               provider=provider.name,
               session_id=session.session_id,
               model=config.model if config else "default")
    
    return session