"""Session API Endpoints"""
from typing import Optional
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
import structlog

from jelmore.services.claude_code import session_manager
from jelmore.services.nats import publish_event

router = APIRouter()
logger = structlog.get_logger()


class CreateSessionRequest(BaseModel):
    """Request model for creating a session"""
    query: str = Field(..., description="Initial query for Claude Code")


class SessionResponse(BaseModel):
    """Response model for session data"""
    id: str
    status: str
    current_directory: str
    created_at: str
    last_activity: str
    output_buffer_size: int


class SendInputRequest(BaseModel):
    """Request model for sending input to a session"""
    input: str = Field(..., description="Input text to send")


@router.post("", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest):
    """Create a new Claude Code session"""
    try:
        session = await session_manager.create_session(request.query)
        
        # Publish event
        await publish_event(
            "session.created",
            session.session_id,
            {"query": request.query, "status": session.status}
        )
        
        return SessionResponse(**session.to_dict())
    except Exception as e:
        logger.error("Failed to create session", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get session details"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse(**session.to_dict())


@router.get("", response_model=list[SessionResponse])
async def list_sessions():
    """List all active sessions"""
    sessions = session_manager.list_sessions()
    return [SessionResponse(**s) for s in sessions]


@router.delete("/{session_id}")
async def terminate_session(session_id: str):
    """Terminate a session"""
    success = await session_manager.terminate_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Publish event
    await publish_event(
        "session.terminated",
        session_id,
        {"reason": "user_requested"}
    )
    
    return {"message": "Session terminated", "session_id": session_id}


@router.post("/{session_id}/input")
async def send_input(session_id: str, request: SendInputRequest):
    """Send input to a waiting session"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        await session.send_input(request.input)
        
        # Publish event
        await publish_event(
            "session.input_sent",
            session_id,
            {"input": request.input}
        )
        
        return {"message": "Input sent", "session_id": session_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to send input", error=str(e))
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