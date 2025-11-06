"""Database Connection Management"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import structlog

from jelmore.config import get_settings
from jelmore.models.session import Base

settings = get_settings()
logger = structlog.get_logger()

# Create async engine with enhanced connection pooling
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=30,  # 30 seconds timeout for getting connection
    pool_recycle=3600,  # Recycle connections every hour
    pool_pre_ping=True,  # Validate connections before use
)

# Create session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """Initialize database"""
    try:
        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized")
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        raise


async def close_db():
    """Close database connections"""
    await engine.dispose()
    logger.info("Database connections closed")


async def get_session() -> AsyncSession:
    """Get database session"""
    async with async_session_maker() as session:
        yield session


async def get_session_stats():
    """Get database connection pool statistics"""
    try:
        pool = engine.pool
        
        stats = {
            "pool_size": pool.size(),
            "checked_in_connections": pool.checkedin(),
            "checked_out_connections": pool.checkedout(),
            "overflow_connections": pool.overflow(),
            "invalid_connections": pool.invalid(),
            "total_connections": pool.size() + pool.overflow()
        }
        
        # Add engine info
        stats.update({
            "pool_timeout": 30,
            "pool_recycle": 3600,
            "max_overflow": settings.database_max_overflow,
            "engine_disposed": engine.is_disposed
        })
        
        return stats
        
    except Exception as e:
        logger.error("Failed to get database stats", error=str(e))
        return {"error": str(e)}