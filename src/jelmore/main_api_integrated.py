"""Jelmore - Integrated REST API with WebSocket, SSE, and Full Infrastructure

Complete FastAPI application integrating:
- Session-based API with database persistence
- WebSocket real-time communication
- Server-Sent Events (SSE) for streaming
- Rate limiting and authentication
- Health checks and metrics
- NATS event bus integration
- Redis caching layer
- PostgreSQL persistence
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any, Optional, List
from datetime import datetime

from fastapi import (
    FastAPI, 
    Depends, 
    Request, 
    HTTPException, 
    WebSocket, 
    WebSocketDisconnect,
    Query,
    BackgroundTasks
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.security import HTTPBearer
import structlog
import json

# Prometheus metrics
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    logger = structlog.get_logger()
    logger.warning("Prometheus client not available, metrics disabled")

# Import application services
from jelmore.config import get_settings
from jelmore.middleware.logging import setup_logging, request_logging_middleware
from jelmore.middleware.auth import api_key_dependency, get_api_key_auth
from jelmore.services.session_service import SessionService, get_session_service
from jelmore.models.session import SessionStatus
from jelmore.models.events import EventType

# Import infrastructure services
from jelmore.services.database import init_db, close_db
from jelmore.services.redis import init_redis, close_redis
from jelmore.services.nats import init_nats, close_nats, publish_event

# Import API utilities
from jelmore.api.websocket_manager import get_websocket_manager, cleanup_websocket_manager
from jelmore.middleware.rate_limiting import get_rate_limiter, cleanup_rate_limiter

# Import Pydantic models
from pydantic import BaseModel, Field

settings = get_settings()
setup_logging()
logger = structlog.get_logger("jelmore.api_integrated")

# Security
security = HTTPBearer()

# Metrics (if available)
if METRICS_AVAILABLE:
    REQUEST_COUNT = Counter('jelmore_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
    REQUEST_DURATION = Histogram('jelmore_request_duration_seconds', 'Request duration')
    ACTIVE_SESSIONS = Gauge('jelmore_active_sessions', 'Number of active sessions')
    WEBSOCKET_CONNECTIONS = Gauge('jelmore_websocket_connections', 'Active WebSocket connections')


# API Request/Response Models
class SessionCreateRequest(BaseModel):
    """Request to create a new session"""
    query: str = Field(..., description="Initial query for Claude Code")
    user_id: Optional[str] = Field(None, description="Optional user identifier")
    current_directory: Optional[str] = Field(None, description="Working directory")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Session metadata")
    timeout_minutes: Optional[int] = Field(None, description="Session timeout in minutes")


class SessionResponse(BaseModel):
    """Response for session data"""
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
    """Request to send input to a session"""
    input: str = Field(..., description="Input text to send")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Input metadata")


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    version: str
    timestamp: float
    infrastructure: Dict[str, Any]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager with PARALLEL infrastructure setup"""
    from jelmore.utils.parallel_init import (
        create_optimized_startup_sequence,
        startup_performance_monitor,
        get_parallel_initializer
    )
    
    startup_start_time = time.time()
    
    logger.info("🚀 Starting Jelmore Integrated API with PARALLEL initialization...", 
                version="1.0.0")
    
    try:
        async with startup_performance_monitor():
            # Create optimized initialization wrappers
            async def init_db_wrapper():
                await init_db()
                return "database_connected"
            
            async def init_redis_wrapper():  
                await init_redis()
                return "redis_connected"
            
            async def init_nats_wrapper():
                await init_nats()
                return "nats_connected"
            
            async def init_session_service_wrapper():
                session_service = await get_session_service()
                app.state.session_service = session_service
                return session_service
            
            async def init_websocket_manager_wrapper():
                ws_manager = await get_websocket_manager()
                app.state.ws_manager = ws_manager
                return ws_manager
            
            async def init_rate_limiter_wrapper():
                try:
                    from jelmore.services.redis import get_redis_client
                    redis_client = await get_redis_client()
                    rate_limiter = await get_rate_limiter(redis_client)
                    logger.info("Rate limiter using Redis backend")
                    app.state.rate_limiter = rate_limiter
                    return rate_limiter
                except Exception as e:
                    logger.warning("Redis unavailable for rate limiting, using in-memory", error=str(e))
                    rate_limiter = await get_rate_limiter(None)
                    app.state.rate_limiter = rate_limiter
                    return rate_limiter
            
            async def init_auth_wrapper():
                auth = get_api_key_auth()
                app.state.auth = auth
                return auth
            
            # Execute PARALLEL infrastructure initialization - the magic!
            startup_metrics = await create_optimized_startup_sequence(
                init_db_wrapper,
                init_redis_wrapper, 
                init_nats_wrapper,
                init_session_service_wrapper,
                init_websocket_manager_wrapper,
                init_rate_limiter_wrapper,
                init_auth_wrapper
            )
            
            # Store metrics for monitoring
            app.state.startup_metrics = startup_metrics
            app.state.parallel_initializer = get_parallel_initializer()
            app.state.start_time = startup_start_time
            
            # Log auth stats after parallel initialization
            if hasattr(app.state, 'auth'):
                auth_stats = await app.state.auth.get_key_stats()
                logger.info("✅ Authentication system ready", **auth_stats)
            
            total_startup_time = time.time() - startup_start_time
            
            logger.info("🎉 Jelmore PARALLEL startup complete!",
                       total_startup_seconds=round(total_startup_time, 3),
                       parallel_init_seconds=round(startup_metrics.parallel_init_time, 3),
                       services_healthy=startup_metrics.services_healthy,
                       services_failed=startup_metrics.services_failed,
                       success_rate=f"{startup_metrics.success_rate:.1f}%",
                       speedup_factor=f"{60/total_startup_time:.1f}x",
                       api_host=settings.api_host,
                       api_port=settings.api_port,
                       max_sessions=settings.max_concurrent_sessions)
        
    except Exception as e:
        logger.error("❌ Failed to initialize Jelmore with parallel startup", 
                    error=str(e), 
                    error_type=type(e).__name__)
        raise
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Jelmore...")
    
    try:
        # Cleanup in reverse order
        await cleanup_rate_limiter()
        await cleanup_websocket_manager()
        
        if hasattr(app.state, 'session_service'):
            await app.state.session_service.stop()
            
        await close_nats()
        await close_redis()  
        await close_db()
        
        logger.info("✅ Jelmore shutdown complete")
        
    except Exception as e:
        logger.error("❌ Error during shutdown", error=str(e))


# Create FastAPI application
app = FastAPI(
    title="Jelmore Integrated API",
    description="Claude Code Session Manager - Complete REST API with WebSocket, SSE, monitoring, and authentication",
    version="1.0.0",
    debug=settings.log_level == "DEBUG",
    lifespan=lifespan,
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc", 
    openapi_url=f"{settings.api_prefix}/openapi.json",
    contact={
        "name": "Jelmore API Support",
        "email": "support@jelmore.ai"
    }
)

# Add middleware
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=settings.cors_origins if settings.cors_origins != ["*"] else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Add request logging middleware
app.middleware("http")(request_logging_middleware)


# Dependency injection helpers
async def get_session_service_dep() -> SessionService:
    """Get session service dependency"""
    return await get_session_service()


async def verify_session_exists(
    session_id: str, 
    session_service: SessionService = Depends(get_session_service_dep)
):
    """Verify session exists"""
    session = await session_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session


# Core API Endpoints
@app.post(f"{settings.api_prefix}/v1/sessions", 
          response_model=SessionResponse, 
          status_code=201, 
          summary="Create Session", 
          tags=["Sessions"])
async def create_session_v1(
    request: Request,
    session_data: SessionCreateRequest,
    background_tasks: BackgroundTasks,
    session_service: SessionService = Depends(get_session_service_dep),
    auth: Dict[str, Any] = Depends(api_key_dependency)
):
    """Create a new Claude Code session"""
    start_time = time.time()
    
    try:
        # Create session with metadata
        session_id = await session_service.create_session(
            query=session_data.query,
            user_id=session_data.user_id or auth.get('user_id'),
            metadata={
                **(session_data.metadata or {}),
                "created_by": auth.get('key_name'),
                "timeout_minutes": session_data.timeout_minutes
            },
            current_directory=session_data.current_directory
        )
        
        # Get created session data
        session = await session_service.get_session(session_id)
        
        # Update metrics
        if METRICS_AVAILABLE:
            REQUEST_COUNT.labels(method="POST", endpoint="/v1/sessions", status="201").inc()
            REQUEST_DURATION.observe(time.time() - start_time)
        
        # Publish creation event
        background_tasks.add_task(
            publish_event,
            EventType.SESSION_CREATED.value,
            session_id,
            {"created_by": auth.get('key_name'), "query": session_data.query}
        )
        
        return SessionResponse(
            session_id=session["session_id"],
            status=session["status"],
            query=session["query"],
            current_directory=session.get("current_directory"),
            user_id=session.get("user_id"),
            claude_process_id=session.get("claude_process_id"),
            metadata=session.get("metadata", {}),
            created_at=session["created_at"].isoformat() if hasattr(session["created_at"], 'isoformat') else str(session["created_at"]),
            updated_at=session["updated_at"].isoformat() if hasattr(session["updated_at"], 'isoformat') else str(session["updated_at"]),
            last_activity=session["last_activity"].isoformat() if session.get("last_activity") and hasattr(session["last_activity"], 'isoformat') else None,
            terminated_at=session["terminated_at"].isoformat() if session.get("terminated_at") and hasattr(session["terminated_at"], 'isoformat') else None,
            output_buffer_size=len(session.get("output_buffer", ""))
        )
        
    except Exception as e:
        if METRICS_AVAILABLE:
            REQUEST_COUNT.labels(method="POST", endpoint="/v1/sessions", status="500").inc()
        logger.error("Failed to create session", error=str(e), user=auth.get('key_name'))
        raise HTTPException(status_code=500, detail=f"Session creation failed: {str(e)}")


@app.get(f"{settings.api_prefix}/v1/sessions/{{session_id}}", 
         response_model=SessionResponse,
         summary="Get Session", 
         tags=["Sessions"])
async def get_session_v1(
    request: Request,
    session_id: str,
    session_service: SessionService = Depends(get_session_service_dep),
    auth: Dict[str, Any] = Depends(api_key_dependency)
):
    """Get session details by ID"""
    start_time = time.time()
    
    try:
        session = await verify_session_exists(session_id, session_service)
        
        if METRICS_AVAILABLE:
            REQUEST_COUNT.labels(method="GET", endpoint="/v1/sessions/{id}", status="200").inc()
            REQUEST_DURATION.observe(time.time() - start_time)
        
        return SessionResponse(
            session_id=session["session_id"],
            status=session["status"],
            query=session["query"],
            current_directory=session.get("current_directory"),
            user_id=session.get("user_id"),
            claude_process_id=session.get("claude_process_id"),
            metadata=session.get("metadata", {}),
            created_at=session["created_at"].isoformat() if hasattr(session["created_at"], 'isoformat') else str(session["created_at"]),
            updated_at=session["updated_at"].isoformat() if hasattr(session["updated_at"], 'isoformat') else str(session["updated_at"]),
            last_activity=session["last_activity"].isoformat() if session.get("last_activity") and hasattr(session["last_activity"], 'isoformat') else None,
            terminated_at=session["terminated_at"].isoformat() if session.get("terminated_at") and hasattr(session["terminated_at"], 'isoformat') else None,
            output_buffer_size=len(session.get("output_buffer", ""))
        )
        
    except HTTPException:
        if METRICS_AVAILABLE:
            REQUEST_COUNT.labels(method="GET", endpoint="/v1/sessions/{id}", status="404").inc()
        raise
    except Exception as e:
        if METRICS_AVAILABLE:
            REQUEST_COUNT.labels(method="GET", endpoint="/v1/sessions/{id}", status="500").inc()
        logger.error("Failed to get session", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve session: {str(e)}")


@app.get(f"{settings.api_prefix}/v1/sessions", 
         response_model=List[SessionResponse],
         summary="List Sessions", 
         tags=["Sessions"])
async def list_sessions_v1(
    request: Request,
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum sessions to return"),
    session_service: SessionService = Depends(get_session_service_dep),
    auth: Dict[str, Any] = Depends(api_key_dependency)
):
    """List sessions with optional filtering"""
    start_time = time.time()
    
    try:
        # Convert status string to enum if provided
        status_filter = None
        if status:
            try:
                status_filter = SessionStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        sessions = await session_service.list_sessions(
            user_id=user_id,
            status=status_filter,
            limit=limit
        )
        
        if METRICS_AVAILABLE:
            REQUEST_COUNT.labels(method="GET", endpoint="/v1/sessions", status="200").inc()
            REQUEST_DURATION.observe(time.time() - start_time)
        
        return [
            SessionResponse(
                session_id=session["session_id"],
                status=session["status"],
                query=session["query"],
                current_directory=session.get("current_directory"),
                user_id=session.get("user_id"),
                claude_process_id=session.get("claude_process_id"),
                metadata=session.get("metadata", {}),
                created_at=session["created_at"].isoformat() if hasattr(session["created_at"], 'isoformat') else str(session["created_at"]),
                updated_at=session["updated_at"].isoformat() if hasattr(session["updated_at"], 'isoformat') else str(session["updated_at"]),
                last_activity=session["last_activity"].isoformat() if session.get("last_activity") and hasattr(session["last_activity"], 'isoformat') else None,
                terminated_at=session["terminated_at"].isoformat() if session.get("terminated_at") and hasattr(session["terminated_at"], 'isoformat') else None,
                output_buffer_size=len(session.get("output_buffer", ""))
            )
            for session in sessions
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        if METRICS_AVAILABLE:
            REQUEST_COUNT.labels(method="GET", endpoint="/v1/sessions", status="500").inc()
        logger.error("Failed to list sessions", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {str(e)}")


@app.delete(f"{settings.api_prefix}/v1/sessions/{{session_id}}", 
           summary="Terminate Session", 
           tags=["Sessions"])
async def terminate_session_v1(
    request: Request,
    session_id: str,
    reason: Optional[str] = Query("User terminated", description="Termination reason"),
    background_tasks: BackgroundTasks,
    session_service: SessionService = Depends(get_session_service_dep),
    auth: Dict[str, Any] = Depends(api_key_dependency)
):
    """Terminate a session"""
    start_time = time.time()
    
    try:
        # Verify session exists
        await verify_session_exists(session_id, session_service)
        
        # Terminate session
        success = await session_service.terminate_session(session_id, reason)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to terminate session")
        
        if METRICS_AVAILABLE:
            REQUEST_COUNT.labels(method="DELETE", endpoint="/v1/sessions/{id}", status="200").inc()
            REQUEST_DURATION.observe(time.time() - start_time)
        
        # Publish termination event
        background_tasks.add_task(
            publish_event,
            EventType.SESSION_TERMINATED.value,
            session_id,
            {"terminated_by": auth.get('key_name'), "reason": reason}
        )
        
        return {
            "message": "Session terminated successfully", 
            "session_id": session_id, 
            "reason": reason
        }
        
    except HTTPException:
        if METRICS_AVAILABLE:
            REQUEST_COUNT.labels(method="DELETE", endpoint="/v1/sessions/{id}", status="404").inc()
        raise
    except Exception as e:
        if METRICS_AVAILABLE:
            REQUEST_COUNT.labels(method="DELETE", endpoint="/v1/sessions/{id}", status="500").inc()
        logger.error("Failed to terminate session", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to terminate session: {str(e)}")


@app.get(f"{settings.api_prefix}/v1/sessions/{{session_id}}/output",
         summary="Get Session Output", 
         tags=["Sessions", "Streaming"])
async def get_session_output_v1(
    request: Request,
    session_id: str,
    session_service: SessionService = Depends(get_session_service_dep),
    auth: Dict[str, Any] = Depends(api_key_dependency)
):
    """Get current session output buffer"""
    start_time = time.time()
    
    try:
        # Verify session exists
        session = await verify_session_exists(session_id, session_service)
        
        # Get output
        output = await session_service.stream_output(session_id)
        
        if METRICS_AVAILABLE:
            REQUEST_COUNT.labels(method="GET", endpoint="/v1/sessions/{id}/output", status="200").inc()
            REQUEST_DURATION.observe(time.time() - start_time)
        
        return {
            "session_id": session_id,
            "output": output or "",
            "output_length": len(output or ""),
            "status": session["status"],
            "retrieved_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        if METRICS_AVAILABLE:
            REQUEST_COUNT.labels(method="GET", endpoint="/v1/sessions/{id}/output", status="404").inc()
        raise
    except Exception as e:
        if METRICS_AVAILABLE:
            REQUEST_COUNT.labels(method="GET", endpoint="/v1/sessions/{id}/output", status="500").inc()
        logger.error("Failed to get session output", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get output: {str(e)}")


@app.get(f"{settings.api_prefix}/v1/sessions/{{session_id}}/stream",
         summary="Stream Session Output (SSE)", 
         tags=["Sessions", "Streaming"])
async def stream_session_output_sse_v1(
    request: Request,
    session_id: str,
    session_service: SessionService = Depends(get_session_service_dep),
    auth: Dict[str, Any] = Depends(api_key_dependency)
):
    """Stream session output using Server-Sent Events (SSE)"""
    
    # Verify session exists
    await verify_session_exists(session_id, session_service)
    
    async def event_stream():
        """Generate SSE events for session output"""
        try:
            # Send initial connection event
            yield f"event: connected\\ndata: {json.dumps({'session_id': session_id, 'timestamp': datetime.utcnow().isoformat()})}\\n\\n"
            
            last_output_length = 0
            
            while True:
                try:
                    # Get current session status
                    session = await session_service.get_session(session_id)
                    if not session:
                        yield f"event: error\\ndata: {json.dumps({'error': 'Session not found'})}\\n\\n"
                        break
                    
                    # Check if session is terminated
                    if session["status"] in [SessionStatus.TERMINATED.value, SessionStatus.FAILED.value]:
                        yield f"event: terminated\\ndata: {json.dumps({'status': session['status'], 'timestamp': datetime.utcnow().isoformat()})}\\n\\n"
                        break
                    
                    # Get current output
                    current_output = await session_service.stream_output(session_id) or ""
                    current_length = len(current_output)
                    
                    # Send new output if any
                    if current_length > last_output_length:
                        new_output = current_output[last_output_length:]
                        yield f"event: output\\ndata: {json.dumps({'content': new_output, 'timestamp': datetime.utcnow().isoformat()})}\\n\\n"
                        last_output_length = current_length
                    
                    # Send status updates
                    yield f"event: status\\ndata: {json.dumps({'status': session['status'], 'timestamp': datetime.utcnow().isoformat()})}\\n\\n"
                    
                    # Wait before next check
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error("SSE stream error", session_id=session_id, error=str(e))
                    yield f"event: error\\ndata: {json.dumps({'error': str(e)})}\\n\\n"
                    break
                    
        except Exception as e:
            logger.error("SSE connection error", session_id=session_id, error=str(e))
            yield f"event: error\\ndata: {json.dumps({'error': 'Connection failed'})}\\n\\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post(f"{settings.api_prefix}/v1/sessions/{{session_id}}/input",
          summary="Send Input to Session", 
          tags=["Sessions", "Input"])
async def send_input_v1(
    request: Request,
    session_id: str,
    input_data: SendInputRequest,
    background_tasks: BackgroundTasks,
    session_service: SessionService = Depends(get_session_service_dep),
    auth: Dict[str, Any] = Depends(api_key_dependency)
):
    """Send input to a waiting session"""
    start_time = time.time()
    
    try:
        # Verify session exists and is in the right state
        session = await verify_session_exists(session_id, session_service)
        
        current_status = SessionStatus(session["status"])
        if current_status not in [SessionStatus.WAITING_INPUT, SessionStatus.ACTIVE]:
            raise HTTPException(
                status_code=400,
                detail=f"Session is not waiting for input (current status: {current_status.value})"
            )
        
        # Update session with input
        await session_service.update_session_status(
            session_id,
            SessionStatus.ACTIVE,
            output_data=f"\\nUser Input: {input_data.input}\\n"
        )
        
        if METRICS_AVAILABLE:
            REQUEST_COUNT.labels(method="POST", endpoint="/v1/sessions/{id}/input", status="200").inc()
            REQUEST_DURATION.observe(time.time() - start_time)
        
        # Notify WebSocket clients
        ws_manager = app.state.ws_manager
        background_tasks.add_task(
            ws_manager.send_to_session,
            session_id,
            {
                "event": "input_received",
                "content": input_data.input,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        # Publish event
        background_tasks.add_task(
            publish_event,
            EventType.COMMAND_EXECUTED.value,
            session_id,
            {"input": input_data.input, "sent_by": auth.get('key_name')}
        )
        
        return {
            "message": "Input sent successfully",
            "session_id": session_id,
            "input_length": len(input_data.input)
        }
        
    except HTTPException:
        if METRICS_AVAILABLE:
            REQUEST_COUNT.labels(method="POST", endpoint="/v1/sessions/{id}/input", status="400").inc()
        raise
    except Exception as e:
        if METRICS_AVAILABLE:
            REQUEST_COUNT.labels(method="POST", endpoint="/v1/sessions/{id}/input", status="500").inc()
        logger.error("Failed to send input", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to send input: {str(e)}")


# WebSocket endpoint for real-time communication
@app.websocket(f"{settings.api_prefix}/v1/sessions/{{session_id}}/ws")
async def websocket_session_v1(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time bidirectional session communication"""
    
    try:
        # Get WebSocket manager
        ws_manager = app.state.ws_manager
        
        # Connect to WebSocket manager
        connection = await ws_manager.connect(websocket, session_id)
        
        # Verify session exists
        session_service = await get_session_service()
        session = await session_service.get_session(session_id)
        
        if not session:
            await websocket.send_json({"event": "error", "message": "Session not found"})
            await websocket.close(code=4004)
            return
        
        # Send initial session state
        await websocket.send_json({
            "event": "session_info",
            "session_id": session_id,
            "status": session["status"],
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Start output streaming task
        stream_task = asyncio.create_task(
            stream_output_to_websocket(websocket, session_id, session_service)
        )
        
        # Listen for incoming messages
        while True:
            try:
                data = await websocket.receive_json()
                
                # Handle message through WebSocket manager
                response = await ws_manager.handle_message(websocket, data)
                if response:
                    await websocket.send_json(response)
                    
                # Handle specific message types
                await handle_websocket_message(
                    websocket, session_id, data, session_service
                )
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error("WebSocket message error", session_id=session_id, error=str(e))
                await websocket.send_json({
                    "event": "error", 
                    "message": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                })
    
    except Exception as e:
        logger.error("WebSocket connection error", session_id=session_id, error=str(e))
        
    finally:
        # Cleanup
        if 'stream_task' in locals():
            stream_task.cancel()
        if 'ws_manager' in locals() and 'connection' in locals():
            await ws_manager.disconnect(websocket, "Connection ended")


async def stream_output_to_websocket(
    websocket: WebSocket, 
    session_id: str, 
    session_service: SessionService
):
    """Stream session output to WebSocket client"""
    last_output_length = 0
    
    try:
        while True:
            # Get current session
            session = await session_service.get_session(session_id)
            if not session:
                await websocket.send_json({
                    "event": "session_ended",
                    "reason": "Session not found"
                })
                break
            
            # Check if session terminated
            if session["status"] in [SessionStatus.TERMINATED.value, SessionStatus.FAILED.value]:
                await websocket.send_json({
                    "event": "session_ended",
                    "status": session["status"],
                    "timestamp": datetime.utcnow().isoformat()
                })
                break
            
            # Get output
            current_output = await session_service.stream_output(session_id) or ""
            current_length = len(current_output)
            
            # Send new output
            if current_length > last_output_length:
                new_output = current_output[last_output_length:]
                await websocket.send_json({
                    "event": "output",
                    "content": new_output,
                    "timestamp": datetime.utcnow().isoformat()
                })
                last_output_length = current_length
            
            # Send periodic status updates
            await websocket.send_json({
                "event": "status_update",
                "status": session["status"],
                "timestamp": datetime.utcnow().isoformat()
            })
            
            await asyncio.sleep(1)
            
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("WebSocket streaming error", session_id=session_id, error=str(e))
        try:
            await websocket.send_json({
                "event": "stream_error",
                "message": str(e)
            })
        except:
            pass


async def handle_websocket_message(
    websocket: WebSocket, 
    session_id: str, 
    data: Dict[str, Any], 
    session_service: SessionService
):
    """Handle incoming WebSocket messages"""
    
    message_type = data.get("type")
    
    if message_type == "input":
        # Send input to session
        input_text = data.get("content", "")
        await session_service.update_session_status(
            session_id,
            SessionStatus.ACTIVE,
            output_data=f"\\nWebSocket Input: {input_text}\\n"
        )
        
        await websocket.send_json({
            "event": "input_received",
            "content": input_text,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Publish event
        await publish_event(
            EventType.COMMAND_EXECUTED.value,
            session_id,
            {"input": input_text, "source": "websocket"}
        )
        
    elif message_type == "get_status":
        # Send current session status
        session = await session_service.get_session(session_id)
        if session:
            await websocket.send_json({
                "event": "status_response",
                "status": session["status"],
                "output_size": len(session.get("output_buffer", "")),
                "timestamp": datetime.utcnow().isoformat()
            })


# Health and monitoring endpoints
@app.get("/health", 
         response_model=HealthResponse, 
         summary="Health Check", 
         tags=["Monitoring"])
async def health_check():
    """Comprehensive health check endpoint"""
    
    try:
        health_data = {
            "status": "healthy",
            "service": "jelmore-integrated-api",
            "version": "1.0.0", 
            "timestamp": time.time(),
            "infrastructure": {}
        }
        
        # Check database
        try:
            session_service = await get_session_service()
            session_stats = await session_service.get_session_stats()
            health_data["infrastructure"]["session_service"] = {
                "status": "healthy",
                "stats": session_stats
            }
        except Exception as e:
            health_data["infrastructure"]["session_service"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_data["status"] = "degraded"
        
        # Check WebSocket manager
        try:
            ws_manager = app.state.ws_manager
            ws_stats = await ws_manager.get_stats()
            health_data["infrastructure"]["websocket_manager"] = {
                "status": "healthy",
                "stats": ws_stats
            }
        except Exception as e:
            health_data["infrastructure"]["websocket_manager"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_data["status"] = "degraded"
        
        status_code = 200 if health_data["status"] in ["healthy", "degraded"] else 503
        
        return JSONResponse(
            status_code=status_code,
            content=health_data
        )
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "jelmore-integrated-api",
                "version": "1.0.0",
                "error": str(e),
                "timestamp": time.time()
            }
        )


@app.get("/metrics", 
         summary="Prometheus Metrics", 
         tags=["Monitoring"])
async def metrics_endpoint():
    """Prometheus metrics endpoint"""
    if METRICS_AVAILABLE:
        return Response(generate_latest(), media_type="text/plain")
    else:
        return JSONResponse(
            status_code=503,
            content={"error": "Metrics not available - prometheus_client not installed"}
        )


@app.get(f"{settings.api_prefix}/v1/stats",
         summary="System Statistics", 
         tags=["Monitoring"])
async def get_system_stats_v1(
    auth: Dict[str, Any] = Depends(api_key_dependency)
):
    """Get comprehensive system statistics"""
    
    try:
        # Collect all stats
        stats_data = {
            "service": "jelmore-integrated-api",
            "version": "1.0.0",
            "timestamp": time.time(),
            "uptime_seconds": time.time() - app.state.get("start_time", time.time())
        }
        
        # Session stats
        try:
            session_service = await get_session_service()
            session_stats = await session_service.get_session_stats()
            stats_data["session_stats"] = session_stats
            
            if METRICS_AVAILABLE:
                ACTIVE_SESSIONS.set(session_stats.get("active_sessions_count", 0))
        except Exception as e:
            stats_data["session_stats"] = {"error": str(e)}
        
        # WebSocket stats
        try:
            ws_manager = app.state.ws_manager
            ws_stats = await ws_manager.get_stats()
            stats_data["websocket_stats"] = ws_stats
            
            if METRICS_AVAILABLE:
                WEBSOCKET_CONNECTIONS.set(ws_stats.get("total_connections", 0))
        except Exception as e:
            stats_data["websocket_stats"] = {"error": str(e)}
        
        # System settings
        stats_data["settings"] = {
            "max_concurrent_sessions": settings.max_concurrent_sessions,
            "session_timeout_seconds": settings.session_default_timeout_seconds,
            "cleanup_interval_seconds": settings.session_cleanup_interval_seconds,
            "api_prefix": settings.api_prefix,
            "cors_origins": settings.cors_origins
        }
        
        return stats_data
        
    except Exception as e:
        logger.error("Stats collection failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Stats unavailable: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 Starting Jelmore Integrated API Server...")
    
    uvicorn.run(
        "jelmore.main_api_integrated:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.log_level == "DEBUG",
        log_level=settings.log_level.lower(),
        access_log=True
    )