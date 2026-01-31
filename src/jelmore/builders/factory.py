"""Factory for selecting and creating provider-specific builders."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jelmore.builders.base import CommandBuilder


class CommandBuilderFactory:
    """Factory for creating provider-specific command builders.

    Uses registration pattern to allow dynamic provider addition.
    """

    _builders: dict[str, type["CommandBuilder"]] = {}

    @classmethod
    def register(cls, provider: str, builder_class: type["CommandBuilder"]) -> None:
        """Register a builder class for a provider.

        Args:
            provider: Provider name (e.g., "claude", "gemini", "codex")
            builder_class: The builder class to instantiate for this provider
        """
        cls._builders[provider.lower()] = builder_class

    @classmethod
    def get_builder(cls, provider: str) -> "CommandBuilder":
        """Get a builder instance for the specified provider.

        Args:
            provider: Provider name (e.g., "claude", "gemini", "codex")

        Returns:
            Configured CommandBuilder instance

        Raises:
            ValueError: If provider is not registered
        """
        provider_lower = provider.lower()
        if provider_lower not in cls._builders:
            available = ", ".join(cls._builders.keys()) or "none"
            raise ValueError(
                f"Unknown provider: {provider}. Available providers: {available}"
            )
        return cls._builders[provider_lower]()

    @classmethod
    def available_providers(cls) -> list[str]:
        """Return list of registered provider names."""
        return list(cls._builders.keys())

    @classmethod
    def is_registered(cls, provider: str) -> bool:
        """Check if a provider is registered."""
        return provider.lower() in cls._builders
