"""Configuration management for Jelmore"""

from functools import lru_cache
from typing import List

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # API Settings
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_prefix: str = Field(default="/api/v1", description="API prefix")

    # Database
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://jelmore:jelmore123@localhost:5432/jelmore",
        description="PostgreSQL connection URL",
    )
    database_pool_size: int = Field(default=20, description="Database pool size")
    database_max_overflow: int = Field(default=40, description="Database max overflow")

    # Redis
    redis_url: RedisDsn = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    redis_max_connections: int = Field(default=50, description="Redis max connections")

    # NATS
    nats_url: str = Field(default="nats://localhost:4222", description="NATS server URL")
    nats_cluster_id: str = Field(default="jelmore-cluster", description="NATS cluster ID")
    nats_client_id: str = Field(default="jelmore-api", description="NATS client ID")

    # Claude Code Settings
    claude_code_bin: str = Field(default="claude", description="Claude Code binary path")
    claude_code_max_turns: int = Field(default=10, description="Max turns for Claude Code")
    claude_code_timeout_seconds: int = Field(default=300, description="Claude Code timeout")

    # Session Management
    max_concurrent_sessions: int = Field(default=10, description="Max concurrent sessions")
    session_cleanup_interval_seconds: int = Field(default=60, description="Cleanup interval")
    session_default_timeout_seconds: int = Field(default=3600, description="Session timeout")

    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="json", description="Log format (json or plain)")

    # Security
    api_key_header: str = Field(default="X-API-Key", description="API key header name")
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:3360"],
        description="CORS allowed origins",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
