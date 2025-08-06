"""API endpoints for Jelmore"""

from fastapi import APIRouter
from .sessions import router as sessions_router

# Create main router
router = APIRouter()

# Include sessions router
router.include_router(sessions_router, prefix="/sessions", tags=["sessions"])

__all__ = ["router"]