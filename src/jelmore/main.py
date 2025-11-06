"""Jelmore - Complete API Integration
Main FastAPI Application with Full REST API, WebSocket, SSE, and Infrastructure Integration

This module consolidates the provider-based API and session-based API into a unified system
with comprehensive features including WebSocket, SSE, health checks, metrics, rate limiting,
authentication, versioning, and monitoring.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any, Optional, List
from datetime import datetime, timedelta

from fastapi import (
    FastAPI, 
    Depends, 
    Request, 
    HTTPException, 
    WebSocket, 
    WebSocketDisconnect,
    Query,
    BackgroundTasks,
    Header
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
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

# Rate limiting
try:
    import slowapi
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    RATE_LIMITING_AVAILABLE = True
except ImportError:
    RATE_LIMITING_AVAILABLE = False
    logger = structlog.get_logger()
    logger.warning("Slowapi not available, rate limiting disabled")

# Import all necessary services and models
from jelmore.config import get_settings
from jelmore.middleware.logging import setup_logging, request_logging_middleware
from jelmore.middleware.auth import api_key_dependency, get_api_key_auth
from jelmore.services.session_service import SessionService, get_session_service
from jelmore.services.database import init_db, close_db, get_session_stats as get_db_stats
from jelmore.services.redis import init_redis, close_redis, get_redis_stats
from jelmore.services.nats import init_nats, close_nats, publish_event, get_nats_stats
from jelmore.models.session import SessionStatus
from jelmore.models.events import EventType

# Import API models and schemas
from pydantic import BaseModel, Field

settings = get_settings()
setup_logging()
logger = structlog.get_logger("jelmore.main")

# Rate limiting setup
if RATE_LIMITING_AVAILABLE:
    limiter = Limiter(key_func=get_remote_address)

# Security
security = HTTPBearer()

# Metrics
if METRICS_AVAILABLE:
    REQUEST_COUNT = Counter('jelmore_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
    REQUEST_DURATION = Histogram('jelmore_request_duration_seconds', 'Request duration')
    ACTIVE_SESSIONS = Gauge('jelmore_active_sessions', 'Number of active sessions')
    WEBSOCKET_CONNECTIONS = Gauge('jelmore_websocket_connections', 'Active WebSocket connections')

# WebSocket connection manager
class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.connection_count = 0
    
    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        self.connection_count += 1
        if METRICS_AVAILABLE:
            WEBSOCKET_CONNECTIONS.set(self.connection_count)
        logger.info("WebSocket connected", session_id=session_id, total_connections=self.connection_count)
    
    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        self.connection_count -= 1
        if METRICS_AVAILABLE:
            WEBSOCKET_CONNECTIONS.set(self.connection_count)
        logger.info("WebSocket disconnected", session_id=session_id, total_connections=self.connection_count)
    
    async def send_to_session(self, session_id: str, data: Dict[str, Any]):
        if session_id in self.active_connections:
            disconnected = []
            for websocket in self.active_connections[session_id]:
                try:
                    await websocket.send_json(data)
                except:
                    disconnected.append(websocket)
            
            # Clean up disconnected websockets
            for ws in disconnected:
                self.disconnect(ws, session_id)

ws_manager = WebSocketManager()


# API Models
class SessionCreateRequest(BaseModel):
    """Request to create a new session"""
    query: str = Field(..., description="Initial query for Claude Code")
    user_id: Optional[str] = Field(None, description="Optional user identifier")
    current_directory: Optional[str] = Field(None, description="Working directory")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Session metadata")
    provider: Optional[str] = Field(None, description="Specific provider to use")
    model: Optional[str] = Field(None, description="Specific model to use")
    timeout_minutes: Optional[int] = Field(None, description="Session timeout in minutes")

class SessionResponse(BaseModel):
    """Response for session data"""
    session_id: str
    status: str
    query: str
    current_directory: Optional[str]
    user_id: Optional[str]
    provider: Optional[str] = None
    model: Optional[str] = None
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

class MetricsResponse(BaseModel):
    """Metrics response"""
    service: str
    version: str
    timestamp: float
    session_stats: Dict[str, Any]
    infrastructure_stats: Dict[str, Any]
    system_health: Dict[str, Any]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager"""
    logger.info("🚀 Starting Jelmore Complete API Service...", 
                environment=settings.log_level,
                version="1.0.0")
    
    try:
        # Initialize all infrastructure services in parallel
        init_tasks = [
            init_db(),
            init_redis(),
            init_nats()
        ]
        
        await asyncio.gather(*init_tasks)
        logger.info("✅ All infrastructure services initialized (PostgreSQL, Redis, NATS)")
        
        # Initialize session service (depends on above)
        session_service = await get_session_service()
        app.state.session_service = session_service
        logger.info("✅ Session service initialized")
        
        # Initialize authentication
        auth = get_api_key_auth()
        app.state.auth = auth
        auth_stats = await auth.get_key_stats()
        logger.info("✅ Authentication initialized", **auth_stats)
        
        # Initialize WebSocket manager
        app.state.ws_manager = ws_manager
        logger.info("✅ WebSocket manager initialized")
        
        logger.info("🎉 Jelmore startup complete",
                   api_host=settings.api_host,
                   api_port=settings.api_port,
                   max_sessions=settings.max_concurrent_sessions)
        
    except Exception as e:
        logger.error("❌ Failed to initialize Jelmore", error=str(e), error_type=type(e).__name__)
        raise
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Jelmore...")
    
    try:
        # Shutdown in parallel
        shutdown_tasks = [
            close_nats(),
            close_redis(),
            close_db()
        ]
        
        if hasattr(app.state, 'session_service'):
            shutdown_tasks.append(app.state.session_service.stop())
            
        await asyncio.gather(*shutdown_tasks, return_exceptions=True)
        logger.info("✅ Jelmore shutdown complete")
        
    except Exception as e:
        logger.error("❌ Error during shutdown", error=str(e))


# Create FastAPI app with comprehensive configuration
app = FastAPI(
    title="Jelmore Complete API",
    description="Claude Code Session Manager - Complete REST API with WebSocket, SSE, monitoring, and authentication",
    version="1.0.0",
    debug=settings.log_level == "DEBUG",
    lifespan=lifespan,
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc", 
    openapi_url=f"{settings.api_prefix}/openapi.json",
    contact={
        "name": "Jelmore API Support",
        "url": "https://github.com/jelmore/jelmore",
        "email": "support@jelmore.ai"
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT"
    }
)

# Add security and middleware
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

# Add rate limiting if available
if RATE_LIMITING_AVAILABLE:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add request logging middleware
app.middleware("http")(request_logging_middleware)


# Dependency injection
async def get_session_service_dep() -> SessionService:
    """Get session service dependency"""
    return await get_session_service()

async def verify_session_exists(session_id: str, session_service: SessionService = Depends(get_session_service_dep)):
    """Verify session exists"""
    session = await session_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session

# Rate limiting decorator helper
def rate_limit(limit_string: str):
    """Rate limiting decorator that works regardless of slowapi availability"""
    def decorator(func):
        if RATE_LIMITING_AVAILABLE:
            return limiter.limit(limit_string)(func)
        return func
    return decorator


# API Endpoints - Version 1
@app.post(f"{settings.api_prefix}/v1/sessions", response_model=SessionResponse, 
          status_code=201, summary="Create Session", tags=["Sessions"])
@rate_limit("10/minute")
async def create_session_v1(
    request: Request,
    session_data: SessionCreateRequest,
    background_tasks: BackgroundTasks,
    session_service: SessionService = Depends(get_session_service_dep),
    auth: Dict[str, Any] = Depends(api_key_dependency)
):
    """Create a new Claude Code session with comprehensive configuration"""
    start_time = time.time()
    
    try:
        # Create session with extended parameters
        session_id = await session_service.create_session(
            query=session_data.query,
            user_id=session_data.user_id or auth.get('user_id'),
            metadata={
                **(session_data.metadata or {}),
                "created_by": auth.get('key_name'),
                "provider": session_data.provider,
                "model": session_data.model,
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
            provider=session_data.provider,
            model=session_data.model,
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


@app.get(f"{settings.api_prefix}/v1/sessions/{{session_id}}", response_model=SessionResponse,
         summary="Get Session", tags=["Sessions"])
@rate_limit("30/minute")
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


@app.get(f"{settings.api_prefix}/v1/sessions", response_model=List[SessionResponse],
         summary="List Sessions", tags=["Sessions"])
@rate_limit("20/minute")
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
           summary="Terminate Session", tags=["Sessions"])
@rate_limit("10/minute")
async def terminate_session_v1(
    request: Request,
    session_id: str,
    background_tasks: BackgroundTasks,
    reason: Optional[str] = Query("User terminated", description="Termination reason"),
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
        
        return {"message": "Session terminated successfully", "session_id": session_id, "reason": reason}
        
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
         summary="Get Session Output", tags=["Sessions", "Output"])
@rate_limit("60/minute")
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
         summary="Stream Session Output (SSE)", tags=["Sessions", "Streaming"])
@rate_limit("5/minute")
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
            
            # Get session and start streaming
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
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@app.post(f"{settings.api_prefix}/v1/sessions/{{session_id}}/input",
          summary="Send Input to Session", tags=["Sessions", "Input"])
@rate_limit("30/minute")
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
        # Accept WebSocket connection
        await ws_manager.connect(websocket, session_id)
        
        # Verify session exists
        session_service = await get_session_service()
        session = await session_service.get_session(session_id)
        
        if not session:
            await websocket.send_json({"event": "error", "message": "Session not found"})
            await websocket.close(code=4004)
            return
        
        # Send initial session state
        await websocket.send_json({
            "event": "connected",
            "session_id": session_id,
            "status": session["status"],
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Start output streaming task
        stream_task = asyncio.create_task(stream_output_to_websocket(websocket, session_id, session_service))
        
        # Listen for incoming messages
        while True:
            try:
                data = await websocket.receive_json()
                await handle_websocket_message(websocket, session_id, data, session_service)
                
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
        ws_manager.disconnect(websocket, session_id)


async def stream_output_to_websocket(websocket: WebSocket, session_id: str, session_service: SessionService):
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


async def handle_websocket_message(websocket: WebSocket, session_id: str, data: Dict[str, Any], session_service: SessionService):
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
        
    elif message_type == "ping":
        # Respond to ping
        await websocket.send_json({
            "event": "pong",
            "timestamp": datetime.utcnow().isoformat()
        })
        
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
        
    else:
        await websocket.send_json({
            "event": "error",
            "message": f"Unknown message type: {message_type}"
        })


# Health and monitoring endpoints
@app.get("/health", response_model=HealthResponse, 
         summary="Health Check", tags=["Monitoring"])
async def health_check():
    """Comprehensive health check endpoint"""
    
    try:
        # Check all services
        health_data = {
            "status": "healthy",
            "service": "jelmore-complete-api",
            "version": "1.0.0", 
            "timestamp": time.time(),
            "infrastructure": {}
        }
        
        # Check database
        try:
            db_stats = await get_db_stats()
            health_data["infrastructure"]["database"] = {
                "status": "healthy",
                "stats": db_stats
            }
        except Exception as e:
            health_data["infrastructure"]["database"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_data["status"] = "degraded"
        
        # Check Redis
        try:
            redis_stats = await get_redis_stats()
            health_data["infrastructure"]["redis"] = {
                "status": "healthy",
                "stats": redis_stats
            }
        except Exception as e:
            health_data["infrastructure"]["redis"] = {
                "status": "unhealthy", 
                "error": str(e)
            }
            health_data["status"] = "degraded"
        
        # Check NATS
        try:
            nats_stats = await get_nats_stats()
            health_data["infrastructure"]["nats"] = {
                "status": "healthy",
                "stats": nats_stats
            }
        except Exception as e:
            health_data["infrastructure"]["nats"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_data["status"] = "degraded"
        
        # Check session service
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
                "service": "jelmore-complete-api",
                "version": "1.0.0",
                "error": str(e),
                "timestamp": time.time()
            }
        )


@app.get("/metrics", 
         summary="Prometheus Metrics", tags=["Monitoring"])
async def metrics_endpoint():
    """Prometheus metrics endpoint"""
    if METRICS_AVAILABLE:
        return Response(generate_latest(), media_type="text/plain")
    else:
        return JSONResponse(
            status_code=503,
            content={"error": "Metrics not available - prometheus_client not installed"}
        )


@app.get(f"{settings.api_prefix}/v1/metrics", response_model=MetricsResponse,
         summary="System Metrics", tags=["Monitoring"])
async def get_system_metrics_v1(
    auth: Dict[str, Any] = Depends(api_key_dependency)
):
    """Get comprehensive system metrics (requires admin permission)"""
    
    if "admin" not in auth.get("permissions", []):
        raise HTTPException(status_code=403, detail="Admin permission required")
    
    try:
        # Collect all metrics
        metrics_data = {
            "service": "jelmore-complete-api",
            "version": "1.0.0",
            "timestamp": time.time(),
            "session_stats": {},
            "infrastructure_stats": {},
            "system_health": {}
        }
        
        # Get session stats
        try:
            session_service = await get_session_service()
            session_stats = await session_service.get_session_stats()
            metrics_data["session_stats"] = session_stats
            if METRICS_AVAILABLE:
                ACTIVE_SESSIONS.set(session_stats.get("active_sessions_count", 0))
        except Exception as e:
            metrics_data["session_stats"] = {"error": str(e)}
        
        # Get infrastructure stats
        try:
            db_stats = await get_db_stats()
            redis_stats = await get_redis_stats()
            nats_stats = await get_nats_stats()
            
            metrics_data["infrastructure_stats"] = {
                "database": db_stats,
                "redis": redis_stats, 
                "nats": nats_stats,
                "websocket_connections": ws_manager.connection_count
            }
        except Exception as e:
            metrics_data["infrastructure_stats"] = {"error": str(e)}
        
        # System health summary
        metrics_data["system_health"] = {
            "overall_status": "healthy",
            "uptime_seconds": time.time() - app.state.get("start_time", time.time()),
            "settings": {
                "max_concurrent_sessions": settings.max_concurrent_sessions,
                "session_timeout_seconds": settings.session_default_timeout_seconds,
                "cleanup_interval_seconds": settings.session_cleanup_interval_seconds
            }
        }
        
        return metrics_data
        
    except Exception as e:
        logger.error("Metrics collection failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Metrics unavailable: {str(e)}")


@app.get(f"{settings.api_prefix}/v1/stats",
         summary="Session Statistics", tags=["Monitoring"])
async def get_session_stats_v1(
    auth: Dict[str, Any] = Depends(api_key_dependency)
):
    """Get session statistics"""
    
    try:
        session_service = await get_session_service()
        stats = await session_service.get_session_stats()
        return stats
        
    except Exception as e:
        logger.error("Failed to get session stats", error=str(e))
        raise HTTPException(status_code=500, detail=f"Stats unavailable: {str(e)}")


# Add startup time tracking
@app.on_event("startup")
async def track_startup_time():
    app.state.start_time = time.time()


if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 Starting Jelmore Complete API Server...")
    
    uvicorn.run(
        "jelmore.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.log_level == "DEBUG",
        log_level=settings.log_level.lower(),
        access_log=True
    )