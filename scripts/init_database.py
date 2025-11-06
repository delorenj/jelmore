#!/usr/bin/env python3
"""Database initialization script for Jelmore"""

import asyncio
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from jelmore.services.database import init_db
from jelmore.config import get_settings
import structlog

logger = structlog.get_logger()


async def initialize_database():
    """Initialize the database with tables and indexes"""
    settings = get_settings()
    
    logger.info(
        "Initializing database",
        database_url=settings.database_url.replace(settings.postgres_password, "***")
    )
    
    try:
        await init_db()
        logger.info("Database initialization completed successfully")
    except Exception as e:
        logger.error("Database initialization failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(initialize_database())