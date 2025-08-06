"""
Tonzies Configuration Settings
"""
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
    
    # Application
    app_name: str = "Tonzies"
    app_version: str = "0.1.0"
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # API
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default=["*"], description="CORS origins")
    
    # Database
    postgres_host: str = Field(default="localhost", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")
    postgres_user: str = Field(default="tonzies", description="PostgreSQL user")
    postgres_password: str = Field(default="tonzies_dev", description="PostgreSQL password")
    postgres_db: str = Field(default="tonzies", description="PostgreSQL database")
    
    @property
    def database_url(self) -> str:
        """Construct PostgreSQL connection URL"""
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    # Redis
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database")
    
    @property
    def redis_url(self) -> str:
        """Construct Redis connection URL"""
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    # NATS
    nats_url: str = Field(default="nats://localhost:4222", description="NATS server URL")
    nats_subject_prefix: str = Field(default="tonzies", description="NATS subject prefix")
    
    # Claude Code
    claude_code_bin: str = Field(default="claude", description="Claude Code binary path")
    claude_code_max_turns: int = Field(default=10, description="Max turns for Claude Code")
    claude_code_timeout: int = Field(default=300, description="Timeout for Claude Code operations (seconds)")
    
    # Session Management
    session_keepalive_interval: int = Field(default=30, description="Session keepalive check interval (seconds)")
    session_output_buffer_size: int = Field(default=1000, description="Max output lines to buffer")


settings = Settings()
