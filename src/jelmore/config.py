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

    # Application
    app_name: str = Field(default="Jelmore", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")

    # API Settings
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_prefix: str = Field(default="/api/v1", description="API prefix")

    # Database
    postgres_host: str = Field(default="localhost", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")
    postgres_user: str = Field(default="jelmore", description="PostgreSQL user")
    postgres_password: str = Field(default="jelmore_dev", description="PostgreSQL password")
    postgres_db: str = Field(default="jelmore", description="PostgreSQL database")
    database_pool_size: int = Field(default=20, description="Database pool size")
    database_max_overflow: int = Field(default=40, description="Database max overflow")

    @property
    def database_url(self) -> str:
        """Construct PostgreSQL connection URL"""
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    # Redis
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database")
    redis_max_connections: int = Field(default=50, description="Redis max connections")

    @property
    def redis_url(self) -> str:
        """Construct Redis connection URL"""
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # NATS
    nats_url: str = Field(default="nats://localhost:4222", description="NATS server URL")
    nats_subject_prefix: str = Field(default="jelmore", description="NATS subject prefix")

    # Claude Code Settings
    claude_code_bin: str = Field(default="claude", description="Claude Code binary path")
    claude_code_max_turns: int = Field(default=10, description="Max turns for Claude Code")
    claude_code_timeout: int = Field(default=300, description="Claude Code timeout (seconds)")

    # Session Management
    max_concurrent_sessions: int = Field(default=10, description="Max concurrent sessions")
    session_keepalive_interval: int = Field(default=30, description="Session keepalive check interval (seconds)")
    session_output_buffer_size: int = Field(default=1000, description="Max output lines to buffer")

    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="json", description="Log format (json or plain)")

    # Security
    api_key_header: str = Field(default="X-API-Key", description="API key header name")
    cors_origins: List[str] = Field(
        default=["*"],
        description="CORS allowed origins",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
