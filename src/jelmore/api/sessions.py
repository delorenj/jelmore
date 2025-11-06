"""Session API Endpoints"""
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
import structlog

from jelmore.services.session_service import get_session_service
from jelmore.services.nats import publish_event
from jelmore.models.session import SessionStatus

router = APIRouter()
logger = structlog.get_logger()


class CreateSessionRequest(BaseModel):
    """Request model for creating a session"""
    query: str = Field(..., description="Initial query for Claude Code")
    user_id: Optional[str] = Field(None, description="Optional user identifier")
    current_directory: Optional[str] = Field(None, description="Optional working directory")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional session metadata")


class SessionResponse(BaseModel):
    """Response model for session data"""
    session_id: str
    status: str
    query: str
    current_directory: Optional[str]
    user_id: Optional[str]
    claude_process_id: Optional[str]
    metadata: Dict[str, Any]
    created_at: str
    updated_at: str
    last_activity: Optional[str] = None
    terminated_at: Optional[str] = None
    output_buffer_size: int = 0


class SendInputRequest(BaseModel):
    """Request model for sending input to a session"""
    input: str = Field(..., description="Input text to send")


@router.post("", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest):
    """Create a new Claude Code session with integrated service"""
    try:
        session_service = await get_session_service()
        
        session_id = await session_service.create_session(
            query=request.query,
            user_id=request.user_id,
            metadata=request.metadata,
            current_directory=request.current_directory
        )
        
        # Get the created session data
        session_data = await session_service.get_session(session_id)
        if not session_data:
            raise HTTPException(status_code=500, detail="Failed to retrieve created session")
        
        # Events are automatically published by the session service
        return SessionResponse(
            session_id=session_data["session_id"],
            status=session_data["status"],
            query=session_data["query"],
            current_directory=session_data.get("current_directory"),
            user_id=session_data.get("user_id"),
            claude_process_id=session_data.get("claude_process_id"),
            metadata=session_data.get("metadata", {}),
            created_at=session_data["created_at"].isoformat() if hasattr(session_data["created_at"], 'isoformat') else str(session_data["created_at"]),
            updated_at=session_data["updated_at"].isoformat() if hasattr(session_data["updated_at"], 'isoformat') else str(session_data["updated_at"]),
            last_activity=session_data["last_activity"].isoformat() if session_data.get("last_activity") and hasattr(session_data["last_activity"], 'isoformat') else None,
            terminated_at=session_data["terminated_at"].isoformat() if session_data.get("terminated_at") and hasattr(session_data["terminated_at"], 'isoformat') else None,
            output_buffer_size=len(session_data.get("output_buffer", ""))
        )
    except Exception as e:
        logger.error("Failed to create session", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get session details with integrated service"""
    try:
        session_service = await get_session_service()
        session_data = await session_service.get_session(session_id)
        
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return SessionResponse(
            session_id=session_data["session_id"],
            status=session_data["status"],
            query=session_data["query"],
            current_directory=session_data.get("current_directory"),
            user_id=session_data.get("user_id"),
            claude_process_id=session_data.get("claude_process_id"),
            metadata=session_data.get("metadata", {}),
            created_at=session_data["created_at"].isoformat() if hasattr(session_data["created_at"], 'isoformat') else str(session_data["created_at"]),
            updated_at=session_data["updated_at"].isoformat() if hasattr(session_data["updated_at"], 'isoformat') else str(session_data["updated_at"]),
            last_activity=session_data["last_activity"].isoformat() if session_data.get("last_activity") and hasattr(session_data["last_activity"], 'isoformat') else None,
            terminated_at=session_data["terminated_at"].isoformat() if session_data.get("terminated_at") and hasattr(session_data["terminated_at"], 'isoformat') else None,
            output_buffer_size=len(session_data.get("output_buffer", ""))
        )
    except Exception as e:
        logger.error("Failed to get session", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=list[SessionResponse])
async def list_sessions(user_id: Optional[str] = None, status: Optional[str] = None, limit: int = 100):
    """List sessions with optional filtering"""
    try:
        session_service = await get_session_service()
        
        # Convert status string to enum if provided
        status_filter = None
        if status:
            try:
                status_filter = SessionStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        sessions_data = await session_service.list_sessions(
            user_id=user_id,
            status=status_filter,
            limit=limit
        )
        
        return [
            SessionResponse(
                session_id=session_data["session_id"],
                status=session_data["status"],
                query=session_data["query"],
                current_directory=session_data.get("current_directory"),
                user_id=session_data.get("user_id"),
                claude_process_id=session_data.get("claude_process_id"),
                metadata=session_data.get("metadata", {}),
                created_at=session_data["created_at"].isoformat() if hasattr(session_data["created_at"], 'isoformat') else str(session_data["created_at"]),
                updated_at=session_data["updated_at"].isoformat() if hasattr(session_data["updated_at"], 'isoformat') else str(session_data["updated_at"]),
                last_activity=session_data["last_activity"].isoformat() if session_data.get("last_activity") and hasattr(session_data["last_activity"], 'isoformat') else None,
                terminated_at=session_data["terminated_at"].isoformat() if session_data.get("terminated_at") and hasattr(session_data["terminated_at"], 'isoformat') else None,
                output_buffer_size=len(session_data.get("output_buffer", ""))
            )
            for session_data in sessions_data
        ]
    except Exception as e:
        logger.error("Failed to list sessions", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{session_id}")
async def terminate_session(session_id: str, reason: Optional[str] = "User requested"):
    """Terminate a session with integrated service"""
    try:
        session_service = await get_session_service()
        
        # Check if session exists first
        session_data = await session_service.get_session(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")
        
        success = await session_service.terminate_session(session_id, reason)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to terminate session")
        
        # Events are automatically published by the session service
        return {"message": "Session terminated", "session_id": session_id, "reason": reason}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to terminate session", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/output")
async def get_session_output(session_id: str):
    """Get current session output buffer"""
    try:
        session_service = await get_session_service()
        
        # Check if session exists
        session_data = await session_service.get_session(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")
        
        output = await session_service.stream_output(session_id)
        return {
            "session_id": session_id,
            "output": output or "",
            "output_length": len(output or ""),
            "status": session_data["status"]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get session output", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_session_stats():
    """Get comprehensive session statistics"""
    try:
        session_service = await get_session_service()
        stats = await session_service.get_session_stats()
        return stats
    except Exception as e:
        logger.error("Failed to get session stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{session_id}/input")
async def send_input(session_id: str, request: SendInputRequest):
    """Send input to a waiting session"""
    try:
        session_service = await get_session_service()
        
        # Check if session exists and is in the right state
        session_data = await session_service.get_session(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")
        
        current_status = SessionStatus(session_data["status"])
        if current_status not in [SessionStatus.WAITING_INPUT, SessionStatus.ACTIVE]:
            raise HTTPException(
                status_code=400, 
                detail=f"Session is not waiting for input (current status: {current_status.value})"
            )
        
        # Update session with input (this would integrate with Claude Code process)
        # For now, we'll update the status to show input was received
        await session_service.update_session_status(
            session_id,
            SessionStatus.ACTIVE,
            output_data=f"\nUser Input: {request.input}\n"
        )
        
        # Publish event
        await publish_event(
            "command.sent",
            session_id,
            {"input": request.input}
        )
        
        return {"message": "Input sent", "session_id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to send input", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/{session_id}/stream")
async def stream_session(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for streaming session output"""
    session = session_manager.get_session(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return
    
    await websocket.accept()
    
    try:
        async for output in session.stream_output():
            await websocket.send_json(output)
            
            # Publish state change events
            if output.get("type") == "system":
                content = output.get("content", "")
                if "waiting" in content.lower():
                    await publish_event(
                        "session.state_changed",
                        session_id,
                        {"from": "active", "to": "waiting_input"}
                    )
            
            # Track directory changes
            if output.get("type") == "tool_use" and output.get("name") == "bash":
                command = output.get("input", {}).get("command", "")
                if command.startswith("cd "):
                    await publish_event(
                        "session.directory_changed",
                        session_id,
                        {
                            "from": session.current_directory,
                            "to": session.current_directory  # Will be updated by session
                        }
                    )
                # Track git operations
                elif any(cmd in command for cmd in ["git commit", "git push", "git pull", "git merge"]):
                    await publish_event(
                        "session.git_activity",
                        session_id,
                        {"command": command}
                    )
                    
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected", session_id=session_id)
    except Exception as e:
        logger.error("WebSocket error", error=str(e))
        await websocket.close(code=1011, reason=str(e))