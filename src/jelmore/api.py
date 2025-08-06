"""
Jelmore API Endpoints

FastAPI endpoints using the provider abstraction layer.
Provides RESTful API for session management and streaming.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .services import SessionService, get_session_service

router = APIRouter(prefix="/api/v1", tags=["sessions"])


# Request/Response Models
class SessionCreateRequest(BaseModel):
    """Request to create a new session"""
    query: str = Field(..., description="Initial query for the session")
    provider: Optional[str] = Field(None, description="Specific provider to use")
    model: Optional[str] = Field(None, description="Specific model to use")
    config: Optional[Dict[str, Any]] = Field(None, description="Additional configuration")


class SessionCreateResponse(BaseModel):
    """Response from creating a session"""
    session_id: str
    status: str
    model: str
    provider: str
    created_at: str
    current_directory: Optional[str] = None


class MessageRequest(BaseModel):
    """Request to send a message to a session"""
    message: str = Field(..., description="Message to send")


class InputRequest(BaseModel):
    """Request to send input to a waiting session"""
    input_text: str = Field(..., description="Input text to send")


class SessionSuspendResponse(BaseModel):
    """Response from suspending a session"""
    session_id: str
    state: Dict[str, Any]
    suspended_at: str


class SessionResumeRequest(BaseModel):
    """Request to resume a session"""
    state: Dict[str, Any] = Field(..., description="Session state to restore")


class SessionListResponse(BaseModel):
    """Response listing sessions"""
    sessions: List[Dict[str, Any]]
    total_count: int


class SystemStatusResponse(BaseModel):
    """System status response"""
    status: str
    providers: Dict[str, Any]
    sessions: Dict[str, Any]
    timestamp: str


# API Endpoints
@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session(
    request: SessionCreateRequest,
    service: SessionService = Depends(get_session_service)
):
    """Create a new AI session"""
    session_data = await service.create_session(
        query=request.query,
        provider_name=request.provider,
        model=request.model,
        config=request.config
    )
    
    return SessionCreateResponse(
        session_id=session_data["id"],
        status=session_data["status"],
        model=session_data.get("model", "unknown"),
        provider=session_data.get("provider", "unknown"),
        created_at=session_data["created_at"],
        current_directory=session_data.get("current_directory")
    )


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    service: SessionService = Depends(get_session_service)
):
    """Get session details by ID"""
    session_data = await service.get_session(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return session_data


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    request: MessageRequest,
    service: SessionService = Depends(get_session_service)
):
    """Send a message to a session"""
    success = await service.send_message(session_id, request.message)
    return {"success": success, "session_id": session_id}


@router.post("/sessions/{session_id}/input")
async def send_input(
    session_id: str,
    request: InputRequest,
    service: SessionService = Depends(get_session_service)
):
    """Send input to a waiting session"""
    success = await service.send_input(session_id, request.input_text)
    return {"success": success, "session_id": session_id}


@router.get("/sessions/{session_id}/stream")
async def stream_session(
    session_id: str,
    service: SessionService = Depends(get_session_service)
):
    """Stream responses from a session"""
    
    async def generate_stream():
        try:
            async for response in service.stream_session(session_id):
                # Format as Server-Sent Events
                yield f"data: {response}\n\n"
        except Exception as e:
            error_response = {
                "event_type": "error",
                "content": f"Stream error: {e}",
                "timestamp": datetime.utcnow().isoformat(),
                "session_id": session_id
            }
            yield f"data: {error_response}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.delete("/sessions/{session_id}")
async def terminate_session(
    session_id: str,
    service: SessionService = Depends(get_session_service)
):
    """Terminate a session"""
    success = await service.terminate_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {"success": success, "session_id": session_id}


@router.post("/sessions/{session_id}/suspend", response_model=SessionSuspendResponse)
async def suspend_session(
    session_id: str,
    service: SessionService = Depends(get_session_service)
):
    """Suspend a session and return its state"""
    state = await service.suspend_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return SessionSuspendResponse(
        session_id=session_id,
        state=state,
        suspended_at=datetime.utcnow().isoformat()
    )


@router.post("/sessions/{session_id}/resume")
async def resume_session(
    session_id: str,
    request: SessionResumeRequest,
    service: SessionService = Depends(get_session_service)
):
    """Resume a session from suspended state"""
    success = await service.resume_session(session_id, request.state)
    return {"success": success, "session_id": session_id}


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    provider: Optional[str] = None,
    service: SessionService = Depends(get_session_service)
):
    """List all sessions, optionally filtered by provider"""
    sessions = await service.list_sessions(provider_name=provider)
    return SessionListResponse(
        sessions=sessions,
        total_count=len(sessions)
    )


@router.get("/providers")
async def list_providers(
    service: SessionService = Depends(get_session_service)
):
    """List available providers"""
    return {
        "available_providers": service.factory.list_available_providers(),
        "active_providers": service.factory.list_active_providers(),
        "configured_providers": service.factory.list_configured_providers(),
        "default_provider": service.factory._default_provider
    }


@router.get("/providers/{provider_name}")
async def get_provider_info(
    provider_name: str,
    service: SessionService = Depends(get_session_service)
):
    """Get information about a specific provider"""
    provider = await service.factory.get_provider(provider_name)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
    
    health = await provider.health_check()
    metrics = await provider.get_metrics()
    
    return {
        "name": provider.name,
        "health": health,
        "metrics": metrics,
        "capabilities": {
            "streaming": provider.capabilities.supports_streaming,
            "continuation": provider.capabilities.supports_continuation,
            "tools": provider.capabilities.supports_tools,
            "file_operations": provider.capabilities.supports_file_operations,
            "multimodal": provider.capabilities.supports_multimodal,
            "code_execution": provider.capabilities.supports_code_execution,
            "max_sessions": provider.capabilities.max_concurrent_sessions
        },
        "available_models": [
            {
                "name": model.name,
                "version": model.version,
                "capabilities": model.capabilities,
                "context_length": model.context_length,
                "max_tokens": model.max_tokens,
                "cost_per_token": model.cost_per_token
            }
            for model in provider.available_models
        ]
    }


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(
    service: SessionService = Depends(get_session_service)
):
    """Get overall system status"""
    status = await service.get_system_status()
    return SystemStatusResponse(**status)


@router.post("/providers/{provider_name}/health")
async def check_provider_health(
    provider_name: str,
    service: SessionService = Depends(get_session_service)
):
    """Check health of a specific provider"""
    provider = await service.factory.get_provider(provider_name)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
    
    health = await provider.health_check()
    return health


@router.post("/maintenance/cleanup")
async def cleanup_expired_sessions(
    max_age_seconds: int = 3600,
    service: SessionService = Depends(get_session_service)
):
    """Manually trigger cleanup of expired sessions"""
    total_cleaned = 0
    results = {}
    
    for provider_name in service.factory.list_active_providers():
        provider = await service.factory.get_provider(provider_name)
        if provider:
            cleaned = await provider.cleanup_expired_sessions(max_age_seconds)
            results[provider_name] = cleaned
            total_cleaned += cleaned
    
    return {
        "total_cleaned": total_cleaned,
        "by_provider": results,
        "max_age_seconds": max_age_seconds
    }


# Health check endpoint (simple)
@router.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "jelmore-provider-system"
    }