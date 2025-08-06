# Provider Migration Guide

## Overview

This guide helps migrate from the current Claude Code-specific implementation to the new provider abstraction layer in Jelmore. The new system supports multiple AI providers through a unified interface while maintaining backward compatibility.

## Key Changes

### Before (Legacy System)
```python
# app/core/claude_code.py
from app.core.claude_code import ClaudeCodeSession, SessionManager

session_manager = SessionManager()
session = await session_manager.create_session("Hello Claude")
```

### After (Provider System)
```python
# src/jelmore/providers
from jelmore.providers import get_provider_factory, SessionConfig

factory = get_provider_factory()
provider = await factory.get_provider("claude")
session = await provider.create_session("Hello Claude", SessionConfig(model="claude-3-5-sonnet-20241022"))
```

## Migration Steps

### 1. Update Imports

**Old imports:**
```python
from app.core.claude_code import ClaudeCodeSession, SessionManager
from app.models.session import Session, SessionStatus
```

**New imports:**
```python
from jelmore.providers import (
    get_provider_factory,
    SessionConfig,
    SessionStatus,
    StreamEventType,
    create_session_with_auto_selection
)
from jelmore.services import get_session_service
```

### 2. Replace Direct Session Management

**Old pattern:**
```python
# Direct session management
session_manager = SessionManager()
session = await session_manager.create_session(query)

# Stream output
async for data in session.stream_output():
    print(data)

# Cleanup
await session_manager.terminate_session(session_id)
```

**New pattern:**
```python
# Service-layer session management
session_service = await get_session_service()
session_data = await session_service.create_session(query)

# Stream output  
async for response in session_service.stream_session(session_data["session_id"]):
    print(f"[{response['event_type']}] {response['content']}")

# Cleanup
await session_service.terminate_session(session_data["session_id"])
```

### 3. Update API Endpoints

**Old API structure:**
```python
# app/api/sessions.py
@app.post("/sessions")
async def create_session(request: CreateSessionRequest):
    session = await session_manager.create_session(request.query)
    return session.to_dict()
```

**New API structure:**
```python
# jelmore/api.py
@router.post("/sessions")
async def create_session(
    request: SessionCreateRequest,
    service: SessionService = Depends(get_session_service)
):
    session_data = await service.create_session(
        query=request.query,
        provider_name=request.provider,
        model=request.model
    )
    return SessionCreateResponse(**session_data)
```

### 4. Update Configuration

**Old configuration (app/config.py):**
```python
class Settings(BaseSettings):
    claude_code_bin: str = "claude"
    claude_code_max_turns: int = 10
    claude_code_timeout_seconds: int = 300
```

**New configuration (src/jelmore/providers/config.py):**
```python
# Environment variables
JELMORE_DEFAULT_PROVIDER=claude
JELMORE_CLAUDE_BIN=/path/to/claude
JELMORE_CLAUDE_DEFAULT_MODEL=claude-3-5-sonnet-20241022
JELMORE_OPENCODE_ENABLED=true
JELMORE_LOAD_BALANCING=true

# Or JSON configuration file
{
  "default_provider": "claude",
  "providers": {
    "claude": {
      "claude_bin": "claude",
      "default_model": "claude-3-5-sonnet-20241022"
    },
    "opencode": {
      "enabled": true,
      "api_endpoint": "http://localhost:8080"
    }
  }
}
```

## Backward Compatibility

### Legacy Endpoint Support

The new system includes legacy endpoints for smooth transition:

```python
# Legacy endpoint (still works)
GET /api/v1/legacy/sessions

# New endpoint (recommended)
GET /api/v1/sessions
```

### Gradual Migration Strategy

1. **Phase 1**: Deploy new system alongside old system
2. **Phase 2**: Route new requests to new system, maintain old endpoints
3. **Phase 3**: Migrate existing sessions to new system  
4. **Phase 4**: Remove old system

### Code Migration Pattern

```python
# Use feature flag for gradual rollout
USE_PROVIDER_SYSTEM = os.getenv("USE_PROVIDER_SYSTEM", "false").lower() == "true"

if USE_PROVIDER_SYSTEM:
    # New provider system
    session_service = await get_session_service()
    session_data = await session_service.create_session(query)
else:
    # Legacy system
    session_manager = SessionManager()
    session = await session_manager.create_session(query)
```

## New Capabilities

### Multiple Provider Support

```python
# Create session with specific provider
await session_service.create_session(
    query="Code review task",
    provider_name="claude",  # Use Claude for code tasks
    model="claude-3-5-sonnet-20241022"
)

await session_service.create_session(
    query="Simple question", 
    provider_name="opencode",  # Use OpenCode for cost optimization
    model="deepseek-v3"
)
```

### Auto-Selection

```python
# Automatic provider selection based on requirements
session_data = await create_session_with_auto_selection(
    query="Analyze this codebase",
    requirements={
        "capabilities": ["tools", "file_operations"],
        "load_balancing": True,
        "cost_optimization": False
    }
)
```

### Enhanced Session Management

```python
# Suspend and resume sessions
state = await session_service.suspend_session(session_id)
# ... later ...
await session_service.resume_session(session_id, state)

# Provider-specific sessions
claude_sessions = await session_service.list_sessions(provider_name="claude")
opencode_sessions = await session_service.list_sessions(provider_name="opencode")
```

## Performance Improvements

### Resource Management

- **Connection Pooling**: Reuse provider connections
- **Session Limits**: Per-provider concurrency control
- **Cleanup Tasks**: Automatic expired session cleanup
- **Health Monitoring**: Provider health checks

### Cost Optimization

```python
# Cost-aware session creation
requirements = {
    "cost_optimization": True,  # Prefer cheaper models
    "model": "auto",  # Let system choose
    "max_tokens": 1000
}

session = await create_session_with_auto_selection(
    query="Simple task",
    requirements=requirements
)
```

### Load Balancing

```python
# Distribute load across providers
for i in range(10):
    session = await create_session_with_auto_selection(
        query=f"Task {i}",
        requirements={"load_balancing": True}
    )
```

## Testing Migration

### Unit Tests

**Old tests:**
```python
def test_claude_session():
    session = ClaudeCodeSession()
    assert session.session_id is not None
```

**New tests:**
```python
@pytest.mark.asyncio
async def test_provider_session():
    factory = get_provider_factory()
    provider = await factory.create_provider("claude", config)
    session = await provider.create_session("test")
    assert session.session_id is not None
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_multi_provider_integration():
    service = await get_session_service()
    
    # Test Claude session
    claude_session = await service.create_session(
        query="Claude task",
        provider_name="claude"
    )
    
    # Test OpenCode session
    opencode_session = await service.create_session(
        query="OpenCode task", 
        provider_name="opencode"
    )
    
    # Verify both work
    assert claude_session["status"] in ["active", "idle"]
    assert opencode_session["status"] in ["active", "idle"]
```

## Monitoring and Observability

### Health Checks

```python
# Check all providers
health_results = await factory.health_check_all()
for provider_name, health in health_results.items():
    print(f"{provider_name}: {health['status']}")

# System-wide status
status = await session_service.get_system_status()
print(f"Active sessions: {status['sessions']['active']}")
```

### Metrics Collection

```python
# Provider metrics
metrics = await factory.get_provider_metrics()
print(f"Total providers: {metrics['total_providers']}")
print(f"Active sessions: {metrics['providers']['claude']['active_sessions']}")

# Session metrics per provider
for provider_name in factory.list_active_providers():
    provider = await factory.get_provider(provider_name)
    provider_metrics = await provider.get_metrics()
    print(f"{provider_name}: {provider_metrics['total_sessions']} sessions")
```

## Error Handling

### Old Error Handling

```python
try:
    session = await session_manager.create_session(query)
except Exception as e:
    print(f"Session creation failed: {e}")
```

### New Error Handling

```python
from jelmore.providers import ProviderError, ModelNotSupportedError, SessionError

try:
    session = await service.create_session(query, model="invalid-model")
except ModelNotSupportedError as e:
    print(f"Model not supported: {e}")
except ProviderError as e:
    print(f"Provider error: {e.provider} - {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Deployment Considerations

### Environment Variables

```bash
# Provider system configuration
export JELMORE_DEFAULT_PROVIDER=claude
export JELMORE_CLAUDE_BIN=/usr/local/bin/claude
export JELMORE_CLAUDE_MAX_SESSIONS=10
export JELMORE_OPENCODE_ENABLED=true
export JELMORE_OPENCODE_API_ENDPOINT=http://opencode:8080
export JELMORE_LOAD_BALANCING=true
```

### Docker Configuration

```dockerfile
# Dockerfile updates for provider system
FROM python:3.11-slim

# Install both Claude Code and OpenCode
RUN pip install claude-code opencode

# Copy provider configuration
COPY providers.json /app/config/

# Set environment for provider system
ENV JELMORE_DEFAULT_PROVIDER=claude
ENV JELMORE_CONFIG_FILE=/app/config/providers.json

COPY src/ /app/src/
WORKDIR /app

CMD ["python", "-m", "src.jelmore.main_updated"]
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: jelmore-provider-system
spec:
  replicas: 3
  selector:
    matchLabels:
      app: jelmore
  template:
    spec:
      containers:
      - name: jelmore
        image: jelmore:provider-system
        env:
        - name: JELMORE_DEFAULT_PROVIDER
          value: "claude"
        - name: JELMORE_CLAUDE_MAX_SESSIONS
          value: "10"
        - name: JELMORE_OPENCODE_ENABLED
          value: "true"
        - name: JELMORE_LOAD_BALANCING
          value: "true"
        ports:
        - containerPort: 8000
```

## Rollback Plan

If issues arise, you can quickly rollback:

1. **Feature Flag Rollback**:
   ```python
   # Set environment variable
   export USE_PROVIDER_SYSTEM=false
   ```

2. **Code Rollback**:
   ```python
   # Revert to old main.py
   from jelmore.main import app  # Old version
   # instead of
   from jelmore.main_updated import app  # New version
   ```

3. **Database Rollback**:
   - Keep old session tables alongside new ones
   - Migrate data back if needed

## Best Practices

### Configuration Management

- Use environment variables for deployment-specific settings
- Use configuration files for complex provider settings
- Validate configuration on startup
- Document all configuration options

### Error Handling

- Catch provider-specific errors appropriately
- Implement fallback mechanisms
- Log errors with sufficient context
- Monitor error rates per provider

### Performance

- Monitor session counts per provider
- Implement session limits
- Use health checks for provider selection
- Clean up expired sessions regularly

### Security

- Validate all provider configurations
- Secure API keys and credentials
- Audit provider access logs
- Implement rate limiting per provider

This migration guide provides a comprehensive roadmap for transitioning to the new provider system while maintaining system stability and adding powerful new capabilities.