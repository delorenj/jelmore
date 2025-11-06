"""Events Model for Session Tracking"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, JSON, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
import enum

from .session import Base


class EventType(str, enum.Enum):
    """Event type enumeration"""
    SESSION_CREATED = "session_created"
    SESSION_STARTED = "session_started"
    SESSION_IDLE = "session_idle"
    SESSION_RESUMED = "session_resumed"
    SESSION_TERMINATED = "session_terminated"
    SESSION_FAILED = "session_failed"
    
    # Command events
    COMMAND_SENT = "command_sent"
    COMMAND_EXECUTED = "command_executed"
    COMMAND_FAILED = "command_failed"
    
    # Output events
    OUTPUT_RECEIVED = "output_received"
    ERROR_RECEIVED = "error_received"
    
    # Provider events
    PROVIDER_SWITCHED = "provider_switched"
    PROVIDER_ERROR = "provider_error"
    
    # System events
    KEEPALIVE = "keepalive"
    RESOURCE_WARNING = "resource_warning"
    TIMEOUT_WARNING = "timeout_warning"


class Event(Base):
    """Event model for tracking session activities"""
    __tablename__ = "events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    event_type = Column(Enum(EventType), nullable=False)
    payload = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship to session
    session = relationship("Session", backref="events")
    
    def __repr__(self):
        return f"<Event(id={self.id}, type={self.event_type}, session_id={self.session_id})>"