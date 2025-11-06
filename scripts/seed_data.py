#!/usr/bin/env python3
"""Seed data script for Jelmore database"""

import asyncio
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from jelmore.models.session import Session, SessionStatus
from jelmore.models.events import Event, EventType
from jelmore.services.database import async_session_maker
import structlog

logger = structlog.get_logger()


async def create_seed_data():
    """Create sample data for testing"""
    
    # Sample sessions
    session_data = [
        {
            "id": str(uuid.uuid4()),
            "status": SessionStatus.ACTIVE,
            "query": "Help me build a REST API with FastAPI",
            "current_directory": "/home/user/projects/api",
            "claude_process_id": "claude_001",
            "session_metadata": {"user_id": "test_user_1", "project": "api_demo"}
        },
        {
            "id": str(uuid.uuid4()),
            "status": SessionStatus.IDLE,
            "query": "Debug my Python application",
            "current_directory": "/home/user/projects/debug",
            "claude_process_id": "claude_002",
            "session_metadata": {"user_id": "test_user_2", "project": "debug_app"}
        },
        {
            "id": str(uuid.uuid4()),
            "status": SessionStatus.TERMINATED,
            "query": "Create a machine learning model",
            "current_directory": "/home/user/projects/ml",
            "claude_process_id": None,
            "session_metadata": {"user_id": "test_user_1", "project": "ml_model"},
            "terminated_at": datetime.utcnow() - timedelta(hours=1)
        }
    ]
    
    # Sample events for each session
    event_templates = [
        {"event_type": EventType.SESSION_CREATED, "payload": {"source": "api"}},
        {"event_type": EventType.SESSION_STARTED, "payload": {"provider": "claude"}},
        {"event_type": EventType.COMMAND_SENT, "payload": {"command": "ls -la", "directory": "/home/user"}},
        {"event_type": EventType.COMMAND_EXECUTED, "payload": {"command": "ls -la", "exit_code": 0}},
        {"event_type": EventType.OUTPUT_RECEIVED, "payload": {"lines": 15, "size_bytes": 1024}},
        {"event_type": EventType.KEEPALIVE, "payload": {"status": "healthy"}}
    ]
    
    async with async_session_maker() as session:
        # Create sessions
        db_sessions = []
        for sess_data in session_data:
            db_session = Session(**sess_data)
            session.add(db_session)
            db_sessions.append(db_session)
        
        await session.flush()  # Flush to get IDs
        
        # Create events for each session
        for i, db_session in enumerate(db_sessions):
            base_time = datetime.utcnow() - timedelta(hours=i+1)
            
            for j, event_template in enumerate(event_templates):
                # Skip some events for terminated sessions
                if db_session.status == SessionStatus.TERMINATED and j > 3:
                    continue
                    
                event = Event(
                    session_id=db_session.id,
                    event_type=event_template["event_type"],
                    payload=event_template["payload"],
                    created_at=base_time + timedelta(minutes=j*5)
                )
                session.add(event)
        
        await session.commit()
        logger.info(f"Created {len(session_data)} sessions with sample events")


if __name__ == "__main__":
    asyncio.run(create_seed_data())