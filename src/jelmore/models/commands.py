"""Pydantic models for commands and payloads."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ContinuationMode(str, Enum):
    """How to handle session continuation."""

    NEW = "new"  # Start fresh session
    CONTINUE = "continue"  # Resume most recent session for provider
    RESUME = "resume"  # Resume specific session by ID


class SideEffectType(str, Enum):
    """Type of side effect produced by command execution."""

    COMMAND = "command"  # Triggers another command
    RESPONSE = "response"  # Emits a response event


class HookConfig(BaseModel):
    """Configuration for a hook to attach to command."""

    name: str = Field(..., description="Hook identifier")
    enabled: bool = Field(default=True, description="Whether hook is active")
    priority: int = Field(default=100, description="Execution order (lower = earlier)")
    config: dict[str, Any] = Field(default_factory=dict, description="Hook-specific settings")


class AgentPromptPayload(BaseModel):
    """Payload for agent.prompt Bloodbank events.

    This is the primary input model for both CLI and event-driven invocations.
    """

    provider: str = Field(
        ...,
        description="Target provider (claude, gemini, codex)",
        examples=["claude", "gemini", "codex"],
    )
    prompt: str = Field(..., description="Prompt to send to the provider", min_length=1)
    session_id: str | None = Field(
        default=None,
        description="Session ID for resume mode",
    )
    continuation_mode: ContinuationMode = Field(
        default=ContinuationMode.NEW,
        description="How to handle session state",
    )
    hooks: list[HookConfig] | None = Field(
        default=None,
        description="Hooks to attach to this command",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata for tracing",
    )
    correlation_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Correlation ID for distributed tracing",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "provider": "claude",
                    "prompt": "Write a Python function to calculate fibonacci numbers",
                    "continuation_mode": "new",
                    "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                }
            ]
        }
    }


class SideEffect(BaseModel):
    """Side effect produced during command execution.

    Side effects are queued during execution and processed after
    the command completes successfully.
    """

    type: SideEffectType = Field(..., description="Type of side effect")
    payload: dict[str, Any] = Field(..., description="Side effect payload")
    correlation_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Correlation ID for this side effect",
    )
    parent_correlation_id: str = Field(
        ...,
        description="Correlation ID of the command that produced this",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the side effect was created",
    )


class CommandResult(BaseModel):
    """Result from command execution.

    Contains the output, any errors, side effects, and execution metrics.
    """

    success: bool = Field(..., description="Whether command succeeded")
    output: str | None = Field(default=None, description="Command output")
    error: str | None = Field(default=None, description="Error message if failed")
    side_effects: list[SideEffect] = Field(
        default_factory=list,
        description="Side effects to process",
    )
    execution_time_ms: float = Field(
        default=0.0,
        description="Execution time in milliseconds",
    )
    correlation_id: str = Field(..., description="Correlation ID for tracing")
    session_id: str | None = Field(
        default=None,
        description="Session ID if session was created/used",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional result metadata",
    )

    @property
    def is_error(self) -> bool:
        """Check if result represents an error."""
        return not self.success or self.error is not None
