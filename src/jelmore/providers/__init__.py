"""
Jelmore Provider System

Extensible provider abstraction layer supporting multiple AI providers.
Includes Claude Code, OpenCode, and future providers with unified interfaces.
"""

from typing import Dict, Type
from .base import BaseProvider, ProviderCapabilities, ModelInfo, StreamResponse
from .factory import ProviderFactory, get_provider_factory
from .claude import ClaudeProvider
from .opencode import OpenCodeProvider

__all__ = [
    "BaseProvider",
    "ProviderCapabilities", 
    "ModelInfo",
    "StreamResponse",
    "ProviderFactory",
    "get_provider_factory",
    "ClaudeProvider",
    "OpenCodeProvider",
]

# Provider registry for dynamic discovery
PROVIDER_REGISTRY: Dict[str, Type[BaseProvider]] = {
    "claude": ClaudeProvider,
    "opencode": OpenCodeProvider,
}

def register_provider(name: str, provider_class: Type[BaseProvider]) -> None:
    """Register a new provider type"""
    PROVIDER_REGISTRY[name] = provider_class

def get_available_providers() -> Dict[str, Type[BaseProvider]]:
    """Get all registered provider types"""
    return PROVIDER_REGISTRY.copy()