"""Base Command interface following Gang of Four Command pattern."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jelmore.hooks.base import Hook
    from jelmore.models.commands import CommandResult


@dataclass
class CommandContext:
    """Context passed to commands during execution.

    Contains all state needed for command execution including
    correlation IDs for distributed tracing.
    """

    correlation_id: str
    provider: str
    prompt: str
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    previous_result: "CommandResult | None" = None


class Command(ABC):
    """Abstract base class for all commands.

    Commands encapsulate provider invocations as objects, enabling:
    - Chaining for multi-step workflows
    - Hook attachment for cross-cutting concerns
    - Retry logic via executor
    - Side effect collection
    """

    def __init__(self) -> None:
        self._pre_hooks: list["Hook"] = []
        self._post_hooks: list["Hook"] = []

    def add_pre_hook(self, hook: "Hook") -> "Command":
        """Add a hook to run before command execution."""
        self._pre_hooks.append(hook)
        return self

    def add_post_hook(self, hook: "Hook") -> "Command":
        """Add a hook to run after command execution."""
        self._post_hooks.append(hook)
        return self

    @abstractmethod
    async def invoke(self, context: CommandContext) -> "CommandResult":
        """Execute the command and return result.

        Args:
            context: Execution context with correlation ID and metadata

        Returns:
            CommandResult with output, side effects, and metrics
        """
        ...

    @property
    @abstractmethod
    def provider(self) -> str:
        """Return the provider this command targets."""
        ...


class CommandChain:
    """Chain of commands for multi-step workflows.

    Supports both ordered (sequential) and parallel execution modes.
    Results from previous commands can be passed to subsequent ones.
    """

    def __init__(self, ordered: bool = True) -> None:
        """Initialize command chain.

        Args:
            ordered: If True, execute sequentially passing results forward.
                    If False, execute in parallel (future implementation).
        """
        self._commands: list[Command] = []
        self._ordered = ordered

    def add(self, command: Command) -> "CommandChain":
        """Add a command to the chain."""
        self._commands.append(command)
        return self

    def then(self, command: Command) -> "CommandChain":
        """Fluent alias for add()."""
        return self.add(command)

    @property
    def commands(self) -> list[Command]:
        """Return list of commands in chain."""
        return self._commands.copy()

    @property
    def is_ordered(self) -> bool:
        """Return whether chain executes sequentially."""
        return self._ordered

    def __len__(self) -> int:
        return len(self._commands)

    def __iter__(self):
        return iter(self._commands)
