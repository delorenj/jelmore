"""Base Hook interface for pre/post execution processing."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jelmore.commands.base import CommandContext
    from jelmore.models.commands import CommandResult


class HookPhase(Enum):
    """When the hook should execute."""

    PRE = "pre"
    POST = "post"


@dataclass
class HookResult:
    """Result from hook execution."""

    success: bool
    abort: bool = False  # If True, abort command execution
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Hook(ABC):
    """Abstract base class for execution hooks.

    Hooks implement cross-cutting concerns like:
    - Authentication validation
    - Logging and observability
    - Rate limiting
    - Metrics collection
    """

    def __init__(self, priority: int = 100) -> None:
        """Initialize hook with priority.

        Args:
            priority: Execution order (lower = earlier). Default 100.
        """
        self._priority = priority

    @property
    def priority(self) -> int:
        """Return hook priority for ordering."""
        return self._priority

    @property
    @abstractmethod
    def name(self) -> str:
        """Return hook name for logging."""
        ...

    @abstractmethod
    async def execute_pre(self, context: "CommandContext") -> HookResult:
        """Execute before command invocation.

        Args:
            context: Command context with correlation ID

        Returns:
            HookResult. If abort=True, command will not execute.
        """
        ...

    @abstractmethod
    async def execute_post(
        self,
        context: "CommandContext",
        result: "CommandResult",
    ) -> HookResult:
        """Execute after command invocation.

        Args:
            context: Command context with correlation ID
            result: Result from command execution

        Returns:
            HookResult with any modifications or observations
        """
        ...

    def __lt__(self, other: "Hook") -> bool:
        """Enable sorting by priority."""
        return self._priority < other._priority
