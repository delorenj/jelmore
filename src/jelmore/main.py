"""Main FastAPI application for Jelmore"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from jelmore.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle"""
    # Startup
    logger.info("Starting Jelmore...")
    logger.info(f"API running on {settings.api_host}:{settings.api_port}")
    
    # TODO: Initialize database connection
    # TODO: Initialize Redis connection
    # TODO: Initialize NATS connection
    # TODO: Start background tasks
    
    yield
    
    # Shutdown
    logger.info("Shutting down Jelmore...")
    # TODO: Cleanup connections and resources


# Create FastAPI app
app = FastAPI(
    title="Jelmore",
    description="Claude Code Session Manager - HTTP API for spawning and managing Claude Code sessions",
    version="0.1.0",
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


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "jelmore",
        "version": "0.1.0",
    }


@app.get(f"{settings.api_prefix}/status")
async def status():
    """Get service status and configuration"""
    return {
        "status": "running",
        "max_concurrent_sessions": settings.max_concurrent_sessions,
        "claude_code_bin": settings.claude_code_bin,
        "nats_url": settings.nats_url,
        # TODO: Add actual session counts and system metrics
    }


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
