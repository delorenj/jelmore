"""
Updated Jelmore Main Application

FastAPI application using the new provider abstraction layer.
Integrates with the provider system for clean separation of concerns.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from jelmore.config import get_settings
from jelmore.api import router
from jelmore.services import get_session_service

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle with provider system"""
    # Startup
    logger.info("Starting Jelmore with Provider System...")
    logger.info(f"API running on {settings.api_host}:{settings.api_port}")
    
    try:
        # Initialize session service with provider system
        session_service = await get_session_service()
        
        # Store service in app state for access in endpoints
        app.state.session_service = session_service
        
        # Get initial system status
        status = await session_service.get_system_status()
        logger.info("Provider system initialized", 
                   active_providers=status["providers"]["active"],
                   total_sessions=status["sessions"]["total"])
        
        # TODO: Initialize database connection
        # TODO: Initialize Redis connection  
        # TODO: Initialize NATS connection
        # TODO: Start additional background tasks
        
        yield
        
        # Shutdown
        logger.info("Shutting down Jelmore...")
        
        # Gracefully shutdown session service
        await session_service.shutdown()
        
        # TODO: Cleanup other connections and resources
        logger.info("Jelmore shutdown complete")
        
    except Exception as e:
        logger.error(f"Failed to start Jelmore: {e}")
        raise


# Create FastAPI app with provider system integration
app = FastAPI(
    title="Jelmore",
    description="AI Provider Session Manager - Unified interface for multiple AI providers",
    version="0.2.0",  # Bumped version for provider system
    lifespan=lifespan,
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc", 
    openapi_url=f"{settings.api_prefix}/openapi.json",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "jelmore",
        "version": "0.2.0",
        "provider_system": "enabled",
    }


@app.get(f"{settings.api_prefix}/status")
async def status():
    """Get service status with provider information"""
    session_service = await get_session_service()
    system_status = await session_service.get_system_status()
    
    return {
        "status": "running",
        "version": "0.2.0",
        "max_concurrent_sessions": settings.max_concurrent_sessions,
        "claude_code_bin": settings.claude_code_bin,
        "nats_url": settings.nats_url,
        "provider_system": system_status,
    }


# Legacy endpoints for backward compatibility
@app.get("/api/v1/legacy/sessions")
async def legacy_list_sessions():
    """Legacy endpoint - redirects to new provider system"""
    session_service = await get_session_service()
    sessions = await session_service.list_sessions()
    
    # Convert to legacy format
    legacy_sessions = []
    for session in sessions:
        legacy_sessions.append({
            "id": session["id"],
            "status": session["status"],
            "current_directory": session.get("current_directory"),
            "created_at": session["created_at"],
            "last_activity": session["last_activity"],
            "output_buffer_size": session.get("output_buffer_size", 0),
        })
    
    return legacy_sessions


if __name__ == "__main__":
    import uvicorn
    
    # Configure logging
    logger.remove()
    log_file = Path("logs/jelmore.log")
    log_file.parent.mkdir(exist_ok=True)
    
    if settings.log_format == "json":
        logger.add(
            log_file,
            format="{time} {level} {message}",
            level=settings.log_level,
            serialize=True,
        )
    else:
        logger.add(
            log_file,
            format="{time} {level} {message}",
            level=settings.log_level,
        )
    
    # Add console logging
    logger.add(
        __import__('sys').stdout,
        format="<green>{time}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=settings.log_level,
    )
    
    logger.info("Starting Jelmore with Provider System")
    logger.info(f"Providers: Claude Code, OpenCode")
    logger.info(f"Models: Sonnet, Opus, Haiku, DeepSeek V3, Kimi K2, Qwen 2.5")
    
    uvicorn.run(
        "jelmore.main_updated:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        reload_dirs=["src/jelmore"],
        reload_includes=["*.py"],
    )