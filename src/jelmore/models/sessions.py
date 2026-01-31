"""Pydantic models for session management."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class SessionMetadata(BaseModel):
    """Metadata associated with a session."""

    created_by: str | None = Field(default=None, description="Who created the session")
    source: str = Field(
        default="cli",
        description="Where session originated (cli, bloodbank)",
    )
    tags: list[str] = Field(default_factory=list, description="User-defined tags")
    extra: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class Session(BaseModel):
    """Session state for a provider conversation.

    Sessions persist across invocations, enabling continue/resume semantics.
    """

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique session identifier",
    )
    provider: str = Field(..., description="Provider this session belongs to")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When session was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When session was last updated",
    )
    state: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific session state",
    )
    metadata: SessionMetadata = Field(
        default_factory=SessionMetadata,
        description="Session metadata",
    )
    correlation_ids: list[str] = Field(
        default_factory=list,
        description="Correlation IDs from commands in this session",
    )
    prompt_count: int = Field(default=0, description="Number of prompts in session")
    last_prompt: str | None = Field(default=None, description="Most recent prompt")
    last_response: str | None = Field(default=None, description="Most recent response")

    def add_correlation_id(self, correlation_id: str) -> None:
        """Add a correlation ID to the session history."""
        if correlation_id not in self.correlation_ids:
            self.correlation_ids.append(correlation_id)

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(UTC)

    def record_interaction(self, prompt: str, response: str | None) -> None:
        """Record a prompt/response interaction."""
        self.prompt_count += 1
        self.last_prompt = prompt
        self.last_response = response
        self.touch()

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "provider": "claude",
                    "created_at": "2026-01-29T10:00:00Z",
                    "updated_at": "2026-01-29T10:30:00Z",
                    "prompt_count": 5,
                    "last_prompt": "Write a fibonacci function",
                }
            ]
        }
    }
