"""
API Router
Main API endpoints for Tonzies
"""
from fastapi import APIRouter
from app.api import sessions

router = APIRouter()

# Include session endpoints
router.include_router(sessions.router, prefix="/session", tags=["sessions"])
