"""Tests for Jelmore Pydantic models."""

from datetime import datetime
from uuid import UUID

import pytest

from jelmore.models import (
    AgentPromptPayload,
    CommandResult,
    ContinuationMode,
    HookConfig,
    Session,
    SessionMetadata,
    SideEffect,
    SideEffectType,
)


class TestAgentPromptPayload:
    """Test AgentPromptPayload model."""

    def test_minimal_payload(self) -> None:
        """Payload can be created with minimal required fields."""
        payload = AgentPromptPayload(provider="claude", prompt="Hello, world!")
        assert payload.provider == "claude"
        assert payload.prompt == "Hello, world!"
        assert payload.continuation_mode == ContinuationMode.NEW
        assert payload.session_id is None
        assert payload.hooks is None

    def test_correlation_id_auto_generated(self) -> None:
        """Correlation ID is auto-generated if not provided."""
        payload = AgentPromptPayload(provider="claude", prompt="test")
        # Should be a valid UUID string
        UUID(payload.correlation_id)

    def test_correlation_id_can_be_specified(self) -> None:
        """Correlation ID can be explicitly provided."""
        custom_id = "custom-correlation-123"
        payload = AgentPromptPayload(
            provider="claude", prompt="test", correlation_id=custom_id
        )
        assert payload.correlation_id == custom_id

    def test_full_payload(self) -> None:
        """Payload accepts all optional fields."""
        payload = AgentPromptPayload(
            provider="gemini",
            prompt="Generate code",
            session_id="session-123",
            continuation_mode=ContinuationMode.RESUME,
            hooks=[HookConfig(name="logging", priority=50)],
            metadata={"source": "cli", "user": "test"},
        )
        assert payload.provider == "gemini"
        assert payload.session_id == "session-123"
        assert payload.continuation_mode == ContinuationMode.RESUME
        assert len(payload.hooks) == 1
        assert payload.hooks[0].name == "logging"
        assert payload.metadata["source"] == "cli"

    def test_prompt_min_length(self) -> None:
        """Prompt must have at least 1 character."""
        with pytest.raises(ValueError):
            AgentPromptPayload(provider="claude", prompt="")


class TestSession:
    """Test Session model."""

    def test_session_creation(self) -> None:
        """Session can be created with minimal fields."""
        session = Session(provider="claude")
        assert session.provider == "claude"
        UUID(session.id)  # Should be valid UUID
        assert session.prompt_count == 0
        assert session.correlation_ids == []

    def test_add_correlation_id(self) -> None:
        """Correlation IDs can be added to session."""
        session = Session(provider="claude")
        session.add_correlation_id("corr-1")
        session.add_correlation_id("corr-2")
        session.add_correlation_id("corr-1")  # Duplicate ignored
        assert session.correlation_ids == ["corr-1", "corr-2"]

    def test_record_interaction(self) -> None:
        """Interactions are recorded correctly."""
        session = Session(provider="claude")
        original_updated = session.updated_at

        session.record_interaction("Hello", "Hi there!")

        assert session.prompt_count == 1
        assert session.last_prompt == "Hello"
        assert session.last_response == "Hi there!"
        assert session.updated_at >= original_updated

    def test_touch_updates_timestamp(self) -> None:
        """Touch updates the updated_at timestamp."""
        session = Session(provider="claude")
        original = session.updated_at
        session.touch()
        assert session.updated_at >= original

    def test_session_with_metadata(self) -> None:
        """Session accepts custom metadata."""
        metadata = SessionMetadata(
            created_by="test-user", source="bloodbank", tags=["test", "automated"]
        )
        session = Session(provider="gemini", metadata=metadata)
        assert session.metadata.created_by == "test-user"
        assert session.metadata.source == "bloodbank"
        assert "test" in session.metadata.tags


class TestCommandResult:
    """Test CommandResult model."""

    def test_success_result(self) -> None:
        """Successful result can be created."""
        result = CommandResult(
            success=True,
            output="Command completed",
            correlation_id="corr-123",
        )
        assert result.success is True
        assert result.output == "Command completed"
        assert result.error is None
        assert result.is_error is False

    def test_error_result(self) -> None:
        """Error result can be created."""
        result = CommandResult(
            success=False,
            error="Something went wrong",
            correlation_id="corr-123",
        )
        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.is_error is True

    def test_with_side_effects(self) -> None:
        """Result can include side effects."""
        side_effect = SideEffect(
            type=SideEffectType.RESPONSE,
            payload={"message": "Event emitted"},
            parent_correlation_id="corr-123",
        )
        result = CommandResult(
            success=True,
            output="Done",
            correlation_id="corr-123",
            side_effects=[side_effect],
        )
        assert len(result.side_effects) == 1
        assert result.side_effects[0].type == SideEffectType.RESPONSE

    def test_execution_time(self) -> None:
        """Execution time is tracked."""
        result = CommandResult(
            success=True,
            correlation_id="corr-123",
            execution_time_ms=150.5,
        )
        assert result.execution_time_ms == 150.5


class TestSideEffect:
    """Test SideEffect model."""

    def test_command_side_effect(self) -> None:
        """Command side effect can be created."""
        effect = SideEffect(
            type=SideEffectType.COMMAND,
            payload={"provider": "gemini", "prompt": "Follow-up"},
            parent_correlation_id="parent-123",
        )
        assert effect.type == SideEffectType.COMMAND
        assert effect.payload["provider"] == "gemini"
        UUID(effect.correlation_id)

    def test_response_side_effect(self) -> None:
        """Response side effect can be created."""
        effect = SideEffect(
            type=SideEffectType.RESPONSE,
            payload={"event": "agent.response", "data": {}},
            parent_correlation_id="parent-123",
        )
        assert effect.type == SideEffectType.RESPONSE

    def test_created_at_auto_set(self) -> None:
        """Created at timestamp is auto-set."""
        effect = SideEffect(
            type=SideEffectType.RESPONSE,
            payload={},
            parent_correlation_id="parent-123",
        )
        assert isinstance(effect.created_at, datetime)


class TestContinuationMode:
    """Test ContinuationMode enum."""

    def test_enum_values(self) -> None:
        """Enum has expected values."""
        assert ContinuationMode.NEW.value == "new"
        assert ContinuationMode.CONTINUE.value == "continue"
        assert ContinuationMode.RESUME.value == "resume"

    def test_string_comparison(self) -> None:
        """Enum can be compared to strings."""
        assert ContinuationMode.NEW == "new"
        assert ContinuationMode.CONTINUE == "continue"


class TestHookConfig:
    """Test HookConfig model."""

    def test_minimal_hook(self) -> None:
        """Hook can be created with just name."""
        hook = HookConfig(name="logging")
        assert hook.name == "logging"
        assert hook.enabled is True
        assert hook.priority == 100
        assert hook.config == {}

    def test_full_hook_config(self) -> None:
        """Hook accepts all configuration options."""
        hook = HookConfig(
            name="rate-limit",
            enabled=True,
            priority=50,
            config={"max_requests": 100, "window_seconds": 60},
        )
        assert hook.priority == 50
        assert hook.config["max_requests"] == 100
