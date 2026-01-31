"""Base CommandBuilder interface for constructing commands."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jelmore.commands.base import Command
    from jelmore.hooks.base import Hook


class CommandBuilder(ABC):
    """Abstract builder for constructing provider-specific commands.

    Each provider (Claude, Gemini, Codex) has its own builder that
    knows how to construct commands with provider-specific configuration.
    """

    def __init__(self) -> None:
        self._hooks: list["Hook"] = []
        self._config: dict[str, Any] = {}

    def with_hook(self, hook: "Hook") -> "CommandBuilder":
        """Add a hook to be attached to built commands."""
        self._hooks.append(hook)
        return self

    def with_config(self, **kwargs: Any) -> "CommandBuilder":
        """Add configuration options for the command."""
        self._config.update(kwargs)
        return self

    @abstractmethod
    def build(self, prompt: str, session_id: str | None = None) -> "Command":
        """Build a command for the target provider.

        Args:
            prompt: The prompt to send to the provider
            session_id: Optional session ID for continuation

        Returns:
            Configured Command instance ready for execution
        """
        ...

    @property
    @abstractmethod
    def provider(self) -> str:
        """Return the provider this builder targets."""
        ...
