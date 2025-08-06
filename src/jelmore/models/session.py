"""Database Models"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, JSON, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base
import uuid
import enum

Base = declarative_base()


class SessionStatus(str, enum.Enum):
    """Session status enum"""
    INITIALIZING = "initializing"
    ACTIVE = "active"
    IDLE = "idle"
    WAITING_INPUT = "waiting_input"
    TERMINATED = "terminated"
    FAILED = "failed"


class Session(Base):
    """Session model"""
    __tablename__ = "sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(Enum(SessionStatus), default=SessionStatus.INITIALIZING)
    query = Column(Text, nullable=False)
    current_directory = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    terminated_at = Column(DateTime, nullable=True)
    session_metadata = Column(JSON, default=dict)