"""
Provider Configuration Management

Centralized configuration for all AI providers.
Supports environment-based configuration and validation.
"""

from typing import Any, Dict, List, Optional
from pathlib import Path
from pydantic import BaseModel, Field, validator
import os


class ModelConfig(BaseModel):
    """Configuration for an AI model"""
    name: str
    version: str = "latest"
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    enabled: bool = True
    cost_per_token: Optional[float] = None


class ClaudeProviderConfig(BaseModel):
    """Configuration for Claude provider"""
    enabled: bool = True
    claude_bin: str = Field(default="claude", description="Path to Claude Code binary")
    default_model: str = "claude-3-5-sonnet-20241022"
    max_concurrent_sessions: int = 10
    max_turns: int = 10
    timeout_seconds: int = 300
    models: List[ModelConfig] = Field(default_factory=lambda: [
        ModelConfig(
            name="claude-3-5-sonnet-20241022",
            version="3.5",
            max_tokens=8192,
            temperature=0.7,
            cost_per_token=0.003
        ),
        ModelConfig(
            name="claude-3-opus-20240229", 
            version="3.0",
            max_tokens=4096,
            temperature=0.7,
            cost_per_token=0.015
        ),
        ModelConfig(
            name="claude-3-haiku-20240307",
            version="3.0", 
            max_tokens=4096,
            temperature=0.7,
            cost_per_token=0.00025
        ),
    ])
    
    @validator('claude_bin')
    def validate_claude_bin(cls, v):
        # Check if binary exists in PATH or is absolute path
        if not Path(v).is_absolute():
            import shutil
            if not shutil.which(v):
                raise ValueError(f"Claude binary not found in PATH: {v}")
        elif not Path(v).exists():
            raise ValueError(f"Claude binary not found: {v}")
        return v


class OpenCodeProviderConfig(BaseModel):
    """Configuration for OpenCode provider"""
    enabled: bool = True
    opencode_bin: str = Field(default="opencode", description="Path to OpenCode binary")
    api_endpoint: str = "http://localhost:8080"
    api_key: Optional[str] = None
    default_model: str = "deepseek-v3"
    max_concurrent_sessions: int = 20
    max_turns: int = 10
    timeout_seconds: int = 180
    temperature: float = 0.7
    models: List[ModelConfig] = Field(default_factory=lambda: [
        ModelConfig(
            name="deepseek-v3",
            version="3.0",
            max_tokens=4096,
            temperature=0.7,
            cost_per_token=0.0001
        ),
        ModelConfig(
            name="kimi-k2",
            version="2.0",
            max_tokens=4096,
            temperature=0.7, 
            cost_per_token=0.0002
        ),
        ModelConfig(
            name="qwen2.5-coder",
            version="2.5",
            max_tokens=2048,
            temperature=0.7,
            cost_per_token=0.00005
        ),
    ])


class ProviderSystemConfig(BaseModel):
    """Global provider system configuration"""
    default_provider: str = "claude"
    auto_selection: bool = True
    load_balancing: bool = True
    cost_optimization: bool = False
    health_check_interval: int = 300  # seconds
    session_cleanup_interval: int = 60  # seconds
    max_total_sessions: int = 50
    
    # Provider-specific configurations
    claude: ClaudeProviderConfig = Field(default_factory=ClaudeProviderConfig)
    opencode: OpenCodeProviderConfig = Field(default_factory=OpenCodeProviderConfig)
    
    @validator('default_provider')
    def validate_default_provider(cls, v, values):
        valid_providers = ['claude', 'opencode']
        if v not in valid_providers:
            raise ValueError(f"Default provider must be one of: {valid_providers}")
        return v


def load_provider_config(config_file: Optional[Path] = None) -> ProviderSystemConfig:
    """Load provider configuration from file or environment"""
    
    # Start with default configuration
    config_dict = {}
    
    # Load from file if provided
    if config_file and config_file.exists():
        import json
        with open(config_file) as f:
            file_config = json.load(f)
        config_dict.update(file_config)
    
    # Override with environment variables
    env_overrides = {
        "default_provider": os.getenv("JELMORE_DEFAULT_PROVIDER"),
        "auto_selection": os.getenv("JELMORE_AUTO_SELECTION", "").lower() in ("true", "1"),
        "load_balancing": os.getenv("JELMORE_LOAD_BALANCING", "").lower() in ("true", "1"),
        "cost_optimization": os.getenv("JELMORE_COST_OPTIMIZATION", "").lower() in ("true", "1"),
        "max_total_sessions": os.getenv("JELMORE_MAX_TOTAL_SESSIONS"),
    }
    
    # Claude-specific environment variables
    claude_overrides = {
        "enabled": os.getenv("JELMORE_CLAUDE_ENABLED", "").lower() not in ("false", "0"),
        "claude_bin": os.getenv("JELMORE_CLAUDE_BIN", "claude"),
        "default_model": os.getenv("JELMORE_CLAUDE_DEFAULT_MODEL"),
        "max_concurrent_sessions": os.getenv("JELMORE_CLAUDE_MAX_SESSIONS"),
        "timeout_seconds": os.getenv("JELMORE_CLAUDE_TIMEOUT"),
    }
    
    # OpenCode-specific environment variables
    opencode_overrides = {
        "enabled": os.getenv("JELMORE_OPENCODE_ENABLED", "").lower() not in ("false", "0"),
        "opencode_bin": os.getenv("JELMORE_OPENCODE_BIN", "opencode"),
        "api_endpoint": os.getenv("JELMORE_OPENCODE_API_ENDPOINT"),
        "api_key": os.getenv("JELMORE_OPENCODE_API_KEY"),
        "default_model": os.getenv("JELMORE_OPENCODE_DEFAULT_MODEL"),
        "max_concurrent_sessions": os.getenv("JELMORE_OPENCODE_MAX_SESSIONS"),
        "timeout_seconds": os.getenv("JELMORE_OPENCODE_TIMEOUT"),
    }
    
    # Apply non-None environment overrides
    for key, value in env_overrides.items():
        if value is not None and value != "":
            config_dict[key] = value
    
    # Apply provider-specific overrides
    if "claude" not in config_dict:
        config_dict["claude"] = {}
    for key, value in claude_overrides.items():
        if value is not None and value != "":
            config_dict["claude"][key] = value
    
    if "opencode" not in config_dict:
        config_dict["opencode"] = {}
    for key, value in opencode_overrides.items():
        if value is not None and value != "":
            config_dict["opencode"][key] = value
    
    # Convert string numbers to integers
    for key in ["max_total_sessions"]:
        if key in config_dict and isinstance(config_dict[key], str):
            try:
                config_dict[key] = int(config_dict[key])
            except ValueError:
                pass
    
    for provider_key in ["claude", "opencode"]:
        if provider_key in config_dict:
            for key in ["max_concurrent_sessions", "timeout_seconds", "max_turns"]:
                if key in config_dict[provider_key] and isinstance(config_dict[provider_key][key], str):
                    try:
                        config_dict[provider_key][key] = int(config_dict[provider_key][key])
                    except ValueError:
                        pass
    
    return ProviderSystemConfig(**config_dict)


def get_provider_config_dict(config: ProviderSystemConfig) -> Dict[str, Any]:
    """Convert provider configuration to dictionary format for factory"""
    return {
        "providers": {
            "claude": {
                "enabled": config.claude.enabled,
                "claude_bin": config.claude.claude_bin,
                "default_model": config.claude.default_model,
                "max_concurrent_sessions": config.claude.max_concurrent_sessions,
                "max_turns": config.claude.max_turns,
                "timeout_seconds": config.claude.timeout_seconds,
                "models": [model.dict() for model in config.claude.models],
            },
            "opencode": {
                "enabled": config.opencode.enabled,
                "opencode_bin": config.opencode.opencode_bin,
                "api_endpoint": config.opencode.api_endpoint,
                "api_key": config.opencode.api_key,
                "default_model": config.opencode.default_model,
                "max_concurrent_sessions": config.opencode.max_concurrent_sessions,
                "max_turns": config.opencode.max_turns,
                "timeout_seconds": config.opencode.timeout_seconds,
                "temperature": config.opencode.temperature,
                "models": [model.dict() for model in config.opencode.models],
            },
        },
        "default_provider": config.default_provider,
        "auto_selection": config.auto_selection,
        "load_balancing": config.load_balancing,
        "cost_optimization": config.cost_optimization,
        "health_check_interval": config.health_check_interval,
        "session_cleanup_interval": config.session_cleanup_interval,
        "max_total_sessions": config.max_total_sessions,
    }


# Example configuration file content
EXAMPLE_CONFIG = {
    "default_provider": "claude",
    "auto_selection": True,
    "load_balancing": True,
    "cost_optimization": False,
    "max_total_sessions": 50,
    "providers": {
        "claude": {
            "enabled": True,
            "claude_bin": "claude",
            "default_model": "claude-3-5-sonnet-20241022",
            "max_concurrent_sessions": 10,
            "max_turns": 10,
            "timeout_seconds": 300
        },
        "opencode": {
            "enabled": True,
            "opencode_bin": "opencode",
            "api_endpoint": "http://localhost:8080",
            "default_model": "deepseek-v3",
            "max_concurrent_sessions": 20,
            "max_turns": 10,
            "timeout_seconds": 180,
            "temperature": 0.7
        }
    }
}