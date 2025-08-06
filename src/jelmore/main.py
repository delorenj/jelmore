"""Jelmore - Claude Code Session Manager
Main FastAPI Application with Infrastructure Integration
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any
import time

from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from jelmore.config import get_settings
from jelmore.middleware.logging import setup_logging, request_logging_middleware
from jelmore.middleware.auth import api_key_dependency, get_api_key_auth
from jelmore.storage.session_manager import get_session_manager, cleanup_session_manager
from jelmore.storage.redis_store import cleanup_redis_store

# Import existing components if they exist
try:
    from jelmore.api import router
except ImportError:
    logger = structlog.get_logger()
    logger.warning("API router not found - will create basic endpoints")
    router = None

try:
    from jelmore.services.database import init_db, close_db
    from jelmore.services.redis import init_redis, close_redis
    from jelmore.services.nats import init_nats, close_nats
except ImportError:
    # Fallback to our new infrastructure
    init_db = close_db = None
    init_redis = close_redis = None
    init_nats = close_nats = None

settings = get_settings()

# Setup structured logging (our new system)
setup_logging()
logger = structlog.get_logger("jelmore.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager with integrated infrastructure"""
    logger.info("Starting Jelmore infrastructure...", 
                environment=settings.log_level,
                redis_url=str(settings.redis_url),
                database_url="***configured***")
    
    try:
        # Initialize legacy services if available
        if init_db:
            await init_db()
            logger.info("Legacy database service initialized")
            
        if init_redis:
            await init_redis()
            logger.info("Legacy Redis service initialized")
            
        if init_nats:
            await init_nats()
            logger.info("Legacy NATS service initialized")
        
        # Initialize new session manager (includes Redis connection)
        session_manager = await get_session_manager()
        app.state.session_manager = session_manager
        logger.info("Session manager initialized",
                   cleanup_interval=settings.session_cleanup_interval_seconds)
        
        # Initialize authentication system
        auth = get_api_key_auth()
        app.state.auth = auth
        auth_stats = await auth.get_key_stats()
        logger.info("Authentication system initialized", **auth_stats)
        
        logger.info("Jelmore startup complete",
                   api_host=settings.api_host,
                   api_port=settings.api_port,
                   max_sessions=settings.max_concurrent_sessions)
        
    except Exception as e:
        logger.error("Failed to initialize Jelmore", error=str(e), error_type=type(e).__name__)
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Jelmore infrastructure...")
    
    try:
        # Cleanup new infrastructure
        await cleanup_session_manager()
        await cleanup_redis_store()
        logger.info("New infrastructure cleaned up")
        
        # Cleanup legacy services
        if close_nats:
            await close_nats()
        if close_redis:
            await close_redis()
        if close_db:
            await close_db()
        
        logger.info("Jelmore shutdown complete")
        
    except Exception as e:
        logger.error("Error during shutdown", error=str(e))


# Create FastAPI app
app = FastAPI(
    title="Jelmore",
    description="Claude Code Session Manager - HTTP API for spawning and managing Claude Code sessions with Redis storage, Traefik integration, and API key authentication",
    version="0.1.0",
    debug=settings.log_level == "DEBUG",
    lifespan=lifespan,
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
    openapi_url=f"{settings.api_prefix}/openapi.json",
)

# Add middleware in correct order
app.middleware("http")(request_logging_middleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include existing API router if available
if router:
    app.include_router(router, prefix=settings.api_prefix)
else:
    logger.info("No API router found - using basic endpoints only")


@app.get("/health")
async def health_check():
    """Health check endpoint for load balancer and service discovery"""
    try:
        # Check session manager health
        session_manager = getattr(app.state, 'session_manager', None)
        if session_manager:
            health_status = await session_manager.health_check()
            return {
                "status": "healthy",
                "service": "jelmore",
                "version": "0.1.0",
                "timestamp": time.time(),
                "infrastructure": health_status
            }
        else:
            return {
                "status": "healthy", 
                "service": "jelmore",
                "version": "0.1.0",
                "timestamp": time.time(),
                "infrastructure": {"status": "initializing"}
            }
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "jelmore", 
                "version": "0.1.0",
                "error": str(e)
            }
        )


@app.get("/metrics")
async def metrics(auth: Dict[str, Any] = Depends(api_key_dependency)):
    """Metrics endpoint for monitoring (requires admin permission)"""
    try:
        # Get session statistics
        session_manager = getattr(app.state, 'session_manager', None)
        if session_manager:
            stats = await session_manager.get_stats()
        else:
            stats = {"error": "Session manager not initialized"}
            
        # Get auth statistics  
        auth_system = getattr(app.state, 'auth', None)
        if auth_system:
            auth_stats = await auth_system.get_key_stats()
        else:
            auth_stats = {"error": "Auth system not initialized"}
            
        return {
            "service": "jelmore",
            "version": "0.1.0", 
            "timestamp": time.time(),
            "session_stats": stats,
            "auth_stats": auth_stats,
            "settings": {
                "max_concurrent_sessions": settings.max_concurrent_sessions,
                "session_timeout": settings.session_default_timeout_seconds,
                "cleanup_interval": settings.session_cleanup_interval_seconds
            }
        }
        
    except Exception as e:
        logger.error("Metrics endpoint failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Metrics unavailable: {str(e)}")


@app.get(f"{settings.api_prefix}/status")
async def api_status(auth: Dict[str, Any] = Depends(api_key_dependency)):
    """API status endpoint with authentication"""
    try:
        session_manager = getattr(app.state, 'session_manager', None)
        if session_manager:
            stats = await session_manager.get_stats()
            session_count = stats.get('total_sessions', 0)
        else:
            session_count = 0
            
        return {
            "status": "running",
            "service": "jelmore",
            "version": "0.1.0",
            "authenticated_as": auth.get('key_name', 'unknown'),
            "permissions": auth.get('permissions', []),
            "active_sessions": session_count,
            "max_concurrent_sessions": settings.max_concurrent_sessions,
            "claude_code_bin": settings.claude_code_bin,
            "infrastructure": {
                "redis_connected": stats.get('redis_connected', False) if session_manager else False,
                "session_manager_running": stats.get('manager_running', False) if session_manager else False
            }
        }
        
    except Exception as e:
        logger.error("Status endpoint failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Status unavailable: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    
    # Configure logging
    logger.remove()
    if settings.log_format == "json":
        logger.add(
            "logs/jelmore.log",
            format="{time} {level} {message}",
            level=settings.log_level,
            serialize=True,
        )
    else:
        logger.add(
            "logs/jelmore.log",
            format="{time} {level} {message}",
            level=settings.log_level,
        )
    
    uvicorn.run(
        "jelmore.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
