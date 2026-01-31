"""Tests for Jelmore configuration system."""

import os
from pathlib import Path

import pytest

from jelmore.config.settings import (
    JelmoreSettings,
    LoggingSettings,
    RedisSettings,
    get_config_dir,
    get_data_dir,
    get_cache_dir,
    get_settings,
    reload_settings,
)


class TestXDGDirectories:
    """Test XDG Base Directory compliance."""

    def test_config_dir_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config dir defaults to ~/.config/jelmore."""
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        assert get_config_dir() == Path.home() / ".config" / "jelmore"

    def test_config_dir_xdg_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config dir respects XDG_CONFIG_HOME."""
        monkeypatch.setenv("XDG_CONFIG_HOME", "/custom/config")
        assert get_config_dir() == Path("/custom/config/jelmore")

    def test_data_dir_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Data dir defaults to ~/.local/share/jelmore."""
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        assert get_data_dir() == Path.home() / ".local" / "share" / "jelmore"

    def test_data_dir_xdg_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Data dir respects XDG_DATA_HOME."""
        monkeypatch.setenv("XDG_DATA_HOME", "/custom/data")
        assert get_data_dir() == Path("/custom/data/jelmore")

    def test_cache_dir_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cache dir defaults to ~/.cache/jelmore."""
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        assert get_cache_dir() == Path.home() / ".cache" / "jelmore"

    def test_cache_dir_xdg_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cache dir respects XDG_CACHE_HOME."""
        monkeypatch.setenv("XDG_CACHE_HOME", "/custom/cache")
        assert get_cache_dir() == Path("/custom/cache/jelmore")


class TestRedisSettings:
    """Test Redis configuration."""

    def test_default_values(self) -> None:
        """Redis has sensible defaults."""
        settings = RedisSettings()
        assert settings.host == "localhost"
        assert settings.port == 6379
        assert settings.db == 0
        assert settings.password is None
        assert settings.ssl is False

    def test_url_without_password(self) -> None:
        """URL is built correctly without password."""
        settings = RedisSettings(host="redis.example.com", port=6380, db=1)
        assert settings.url == "redis://redis.example.com:6380/1"

    def test_url_with_password(self) -> None:
        """URL is built correctly with password."""
        settings = RedisSettings(host="localhost", password="secret")
        assert settings.url == "redis://:secret@localhost:6379/0"

    def test_url_with_ssl(self) -> None:
        """URL uses rediss:// protocol with SSL."""
        settings = RedisSettings(ssl=True)
        assert settings.url.startswith("rediss://")

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Settings can be overridden via environment variables."""
        monkeypatch.setenv("JELMORE_REDIS_HOST", "redis.prod.com")
        monkeypatch.setenv("JELMORE_REDIS_PORT", "6380")
        settings = RedisSettings()
        assert settings.host == "redis.prod.com"
        assert settings.port == 6380


class TestLoggingSettings:
    """Test logging configuration."""

    def test_default_values(self) -> None:
        """Logging has sensible defaults."""
        settings = LoggingSettings()
        assert settings.level == "INFO"
        assert settings.format == "json"
        assert settings.file is None

    def test_level_validation(self) -> None:
        """Invalid log levels are rejected."""
        with pytest.raises(ValueError, match="Invalid log level"):
            LoggingSettings(level="INVALID")

    def test_level_case_insensitive(self) -> None:
        """Log level is case insensitive."""
        settings = LoggingSettings(level="debug")
        assert settings.level == "DEBUG"

    def test_format_validation(self) -> None:
        """Invalid formats are rejected."""
        with pytest.raises(ValueError, match="Invalid log format"):
            LoggingSettings(format="xml")


class TestJelmoreSettings:
    """Test main settings class."""

    def test_default_values(self, test_settings: JelmoreSettings) -> None:
        """Main settings have sensible defaults."""
        assert test_settings.debug is False
        assert test_settings.environment == "development"

    def test_environment_validation(self) -> None:
        """Invalid environments are rejected."""
        with pytest.raises(ValueError, match="Invalid environment"):
            JelmoreSettings(environment="invalid")

    def test_nested_settings_work(self, test_settings: JelmoreSettings) -> None:
        """Nested settings objects are accessible."""
        assert test_settings.redis.host == "localhost"
        assert test_settings.rabbitmq.port == 5672
        assert test_settings.logging.level == "INFO"

    def test_get_settings_cached(self) -> None:
        """get_settings returns cached instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_reload_settings_clears_cache(self) -> None:
        """reload_settings returns new instance."""
        settings1 = get_settings()
        settings2 = reload_settings()
        # Different instances but same values
        assert settings1 is not settings2

    def test_directories_created(self, test_settings: JelmoreSettings) -> None:
        """Directories are created on initialization."""
        assert test_settings.config_dir.exists()
        assert test_settings.data_dir.exists()
        assert test_settings.cache_dir.exists()
