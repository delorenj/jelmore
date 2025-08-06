"""
Tonzies - Claude Code Session Manager
Main FastAPI Application
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.config import settings
from app.api import router
from app.core.logging import setup_logging
from app.core.database import init_db, close_db
from app.core.redis_client import init_redis, close_redis
from app.core.nats_client import init_nats, close_nats

# Setup structured logging
setup_logging(settings.log_level)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Starting Tonzies application", version=settings.app_version)
    
    # Startup
    await init_db()
    await init_redis()
    await init_nats()
    
    yield
    
    # Shutdown
    logger.info("Shutting down Tonzies application")
    await close_nats()
    await close_redis()
    await close_db()


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
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
app.include_router(router, prefix=settings.api_prefix)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": settings.app_version}
