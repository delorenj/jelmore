"""Jelmore configuration using Pydantic Settings with XDG support."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_config_dir() -> Path:
    """Get configuration directory following XDG Base Directory spec.

    Returns ~/.config/jelmore by default, or uses XDG_CONFIG_HOME if set.
    """
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        base = Path(xdg_config)
    else:
        base = Path.home() / ".config"
    return base / "jelmore"


def get_data_dir() -> Path:
    """Get data directory following XDG Base Directory spec.

    Returns ~/.local/share/jelmore by default, or uses XDG_DATA_HOME if set.
    """
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        base = Path(xdg_data)
    else:
        base = Path.home() / ".local" / "share"
    return base / "jelmore"


def get_cache_dir() -> Path:
    """Get cache directory following XDG Base Directory spec.

    Returns ~/.cache/jelmore by default, or uses XDG_CACHE_HOME if set.
    """
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache:
        base = Path(xdg_cache)
    else:
        base = Path.home() / ".cache"
    return base / "jelmore"


class RedisSettings(BaseSettings):
    """Redis connection settings."""

    model_config = SettingsConfigDict(
        env_prefix="JELMORE_REDIS_",
        extra="ignore",
    )

    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, description="Redis port")
    db: int = Field(default=0, description="Redis database number")
    password: str | None = Field(default=None, description="Redis password")
    ssl: bool = Field(default=False, description="Use SSL for Redis connection")

    @property
    def url(self) -> str:
        """Build Redis connection URL."""
        protocol = "rediss" if self.ssl else "redis"
        auth = f":{self.password}@" if self.password else ""
        return f"{protocol}://{auth}{self.host}:{self.port}/{self.db}"


class RabbitMQSettings(BaseSettings):
    """RabbitMQ (Bloodbank) connection settings."""

    model_config = SettingsConfigDict(
        env_prefix="JELMORE_RABBITMQ_",
        extra="ignore",
    )

    host: str = Field(default="localhost", description="RabbitMQ host")
    port: int = Field(default=5672, description="RabbitMQ AMQP port")
    username: str = Field(default="guest", description="RabbitMQ username")
    password: str = Field(default="guest", description="RabbitMQ password")
    vhost: str = Field(default="/", description="RabbitMQ virtual host")
    ssl: bool = Field(default=False, description="Use SSL for RabbitMQ connection")

    # Exchange and queue configuration
    exchange: str = Field(default="jelmore.events", description="Event exchange name")
    queue_prefix: str = Field(default="jelmore", description="Queue name prefix")

    @property
    def url(self) -> str:
        """Build RabbitMQ connection URL."""
        protocol = "amqps" if self.ssl else "amqp"
        return f"{protocol}://{self.username}:{self.password}@{self.host}:{self.port}{self.vhost}"


class ProviderSettings(BaseSettings):
    """Provider-specific settings."""

    model_config = SettingsConfigDict(
        env_prefix="JELMORE_PROVIDER_",
        extra="ignore",
    )

    default: str = Field(default="claude", description="Default provider to use")
    timeout_seconds: int = Field(
        default=300, description="Default provider timeout in seconds"
    )

    # Provider-specific API keys (can be overridden per provider)
    claude_api_key: str | None = Field(
        default=None, alias="ANTHROPIC_API_KEY", description="Anthropic API key"
    )
    gemini_api_key: str | None = Field(
        default=None, alias="GEMINI_API_KEY", description="Google Gemini API key"
    )
    codex_api_key: str | None = Field(
        default=None, alias="OPENAI_API_KEY", description="OpenAI Codex API key"
    )


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(
        env_prefix="JELMORE_LOG_",
        extra="ignore",
    )

    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="json", description="Log format (json, console)")
    file: Path | None = Field(default=None, description="Log file path")

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return upper

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        """Validate log format."""
        valid_formats = {"json", "console"}
        lower = v.lower()
        if lower not in valid_formats:
            raise ValueError(f"Invalid log format: {v}. Must be one of {valid_formats}")
        return lower


class SessionSettings(BaseSettings):
    """Session management settings."""

    model_config = SettingsConfigDict(
        env_prefix="JELMORE_SESSION_",
        extra="ignore",
    )

    ttl_hours: int = Field(
        default=24, description="Session TTL in hours (0 = no expiry)"
    )
    max_per_provider: int = Field(
        default=10, description="Maximum sessions per provider"
    )
    auto_cleanup: bool = Field(
        default=True, description="Automatically cleanup expired sessions"
    )


class JelmoreSettings(BaseSettings):
    """Main Jelmore configuration.

    Configuration is loaded from (in order of precedence):
    1. Environment variables (JELMORE_* prefix)
    2. .env file in current directory
    3. Config file at ~/.config/jelmore/config.yaml
    4. Default values

    All settings support environment variable overrides.
    """

    model_config = SettingsConfigDict(
        env_prefix="JELMORE_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Core settings
    debug: bool = Field(default=False, description="Enable debug mode")
    environment: str = Field(
        default="development", description="Environment (development, staging, production)"
    )

    # Directory paths (XDG compliant)
    config_dir: Path = Field(
        default_factory=get_config_dir, description="Configuration directory"
    )
    data_dir: Path = Field(
        default_factory=get_data_dir, description="Data directory"
    )
    cache_dir: Path = Field(
        default_factory=get_cache_dir, description="Cache directory"
    )

    # Nested settings
    redis: RedisSettings = Field(default_factory=RedisSettings)
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    provider: ProviderSettings = Field(default_factory=ProviderSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    session: SessionSettings = Field(default_factory=SessionSettings)

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment setting."""
        valid_envs = {"development", "staging", "production"}
        lower = v.lower()
        if lower not in valid_envs:
            raise ValueError(f"Invalid environment: {v}. Must be one of {valid_envs}")
        return lower

    def ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        for dir_path in [self.config_dir, self.data_dir, self.cache_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def model_post_init(self, __context: Any) -> None:
        """Post-initialization hook to ensure directories exist."""
        if self.environment != "production":
            # Only auto-create in non-production
            self.ensure_directories()


@lru_cache
def get_settings() -> JelmoreSettings:
    """Get cached settings instance.

    Returns a cached singleton instance of JelmoreSettings.
    Use this function to access settings throughout the application.
    """
    return JelmoreSettings()


def reload_settings() -> JelmoreSettings:
    """Reload settings (clears cache).

    Useful for testing or when environment changes.
    """
    get_settings.cache_clear()
    return get_settings()
