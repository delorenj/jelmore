"""Base Provider interface for agentic coding tools."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderConfig:
    """Configuration for a provider.

    Contains common settings applicable to all providers,
    with extensibility for provider-specific options.
    """

    name: str
    enabled: bool = True
    timeout_seconds: int = 300  # 5 minutes default
    max_retries: int = 3
    extra: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value from extra settings."""
        return self.extra.get(key, default)


@dataclass
class ProviderResponse:
    """Response from a provider invocation."""

    success: bool
    output: str | None = None
    error: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Provider(ABC):
    """Abstract base class for provider adapters.

    Each provider (Claude Code, Gemini CLI, Codex) implements this
    interface to provide a consistent way to invoke the tool.
    """

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config

    @property
    def name(self) -> str:
        """Return the provider name."""
        return self._config.name

    @property
    def config(self) -> ProviderConfig:
        """Return the provider configuration."""
        return self._config

    @abstractmethod
    async def invoke(
        self,
        prompt: str,
        session_id: str | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Invoke the provider with the given prompt.

        Args:
            prompt: The prompt to send to the provider
            session_id: Optional session ID for continuation
            **kwargs: Provider-specific options

        Returns:
            ProviderResponse with output and metadata
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is available and configured.

        Returns:
            True if provider is ready, False otherwise
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
