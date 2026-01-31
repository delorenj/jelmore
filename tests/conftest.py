"""Pytest configuration and fixtures for Jelmore tests."""

import os
from pathlib import Path
from typing import Generator

import pytest

from jelmore.config.settings import JelmoreSettings, reload_settings


@pytest.fixture(autouse=True)
def reset_settings() -> Generator[None, None, None]:
    """Reset settings cache before each test."""
    reload_settings()
    yield
    reload_settings()


@pytest.fixture
def test_config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory for testing."""
    config_dir = tmp_path / "config" / "jelmore"
    config_dir.mkdir(parents=True)
    return config_dir


@pytest.fixture
def test_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory for testing."""
    data_dir = tmp_path / "data" / "jelmore"
    data_dir.mkdir(parents=True)
    return data_dir


@pytest.fixture
def test_settings(
    test_config_dir: Path, test_data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> JelmoreSettings:
    """Create test settings with temporary directories."""
    cache_dir = tmp_path / "cache" / "jelmore"
    cache_dir.mkdir(parents=True)

    # Set XDG directories to temporary paths
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    return reload_settings()
