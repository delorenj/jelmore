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

# LEGACY VERSION - ARCHIVED
# This file has been replaced by consolidated main.py
# Kept for reference only

settings = get_settings()
setup_logging()
logger = structlog.get_logger("jelmore.main_original")

print("WARNING: This is an archived version. Use main.py instead.")
