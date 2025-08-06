# Provider Architecture Documentation

## Overview

The Jelmore Provider System implements a clean, extensible abstraction layer that supports multiple AI providers (Claude Code, OpenCode, and future providers) through a unified interface. This architecture follows SOLID principles and provides comprehensive session management, streaming, and lifecycle operations.

## Architecture Principles

### Open/Closed Principle
- **Open for extension**: New providers can be added without modifying existing code
- **Closed for modification**: Core interfaces remain stable as new providers are added

### Interface Segregation
- Clean, focused interfaces for different aspects (session management, streaming, lifecycle)
- Providers only implement what they actually support

### Dependency Inversion
- High-level modules depend on abstractions, not concrete implementations
- Runtime provider selection through dependency injection

### Single Responsibility
- Each provider handles only its own specifics
- Clear separation between coordination and execution

## Core Components

### 1. Base Interfaces (`base.py`)

#### `BaseProvider`
Abstract base class defining the provider contract:
```python
class BaseProvider(ABC):
    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities
    
    @property  
    @abstractmethod
    def available_models(self) -> List[ModelInfo]
    
    @abstractmethod
    async def create_session(self, query: str, config: SessionConfig) -> BaseSession
    
    @abstractmethod
    async def health_check(self) -> Dict[str, Any]
```

#### `BaseSession`
Abstract base class for AI sessions:
```python
class BaseSession(ABC):
    @abstractmethod
    async def start(self, query: str, continue_session: bool = False) -> None
    
    @abstractmethod
    async def stream_output(self) -> AsyncIterator[StreamResponse]
    
    @abstractmethod
    async def terminate(self) -> None
    
    @abstractmethod
    async def suspend(self) -> Dict[str, Any]
    
    @abstractmethod 
    async def resume(self, state: Dict[str, Any]) -> None
```

### 2. Provider Implementations

#### Claude Provider (`claude.py`)
- Wraps Claude Code CLI subprocess management
- Supports all Claude models (Opus, Sonnet, Haiku)
- Full streaming and tool support
- Directory change detection
- Session continuation

#### OpenCode Provider (`opencode.py`)  
- Alternative provider for other AI models
- Supports DeepSeek V3, Kimi K2, Qwen 2.5 Coder
- Conversation history management
- API-based communication (simulated)
- Cost optimization features

### 3. Factory Pattern (`factory.py`)

#### `ProviderFactory`
Centralized factory for provider lifecycle management:
```python
class ProviderFactory:
    async def create_provider(self, name: str, config: Dict) -> BaseProvider
    async def get_or_create_provider(self, name: str) -> BaseProvider
    async def select_best_provider(self, requirements: Dict) -> str
    async def health_check_all(self) -> Dict[str, Dict]
```

#### Auto-Selection Algorithm
The factory includes intelligent provider selection based on:
- **Model requirements**: Match specific model to provider
- **Capabilities**: Ensure provider supports required features
- **Load balancing**: Prefer less loaded providers
- **Cost optimization**: Select cheaper models when appropriate
- **Health status**: Avoid unhealthy providers

### 4. Configuration System (`config.py`)

#### Environment-Based Configuration
```python
# Environment variables
JELMORE_DEFAULT_PROVIDER=claude
JELMORE_CLAUDE_BIN=/path/to/claude
JELMORE_OPENCODE_API_ENDPOINT=http://localhost:8080
JELMORE_LOAD_BALANCING=true
JELMORE_COST_OPTIMIZATION=false
```

#### File-Based Configuration
```json
{
  "default_provider": "claude",
  "auto_selection": true,
  "load_balancing": true,
  "providers": {
    "claude": {
      "enabled": true,
      "claude_bin": "claude",
      "default_model": "claude-3-5-sonnet-20241022",
      "max_concurrent_sessions": 10
    },
    "opencode": {
      "enabled": true,
      "api_endpoint": "http://localhost:8080",
      "default_model": "deepseek-v3",
      "max_concurrent_sessions": 20
    }
  }
}
```

## Session Lifecycle

### 1. Session Creation
```python
# Automatic provider selection
session = await create_session_with_auto_selection(
    query="Help me debug this code",
    requirements={"capabilities": ["tools", "streaming"]},
    config=SessionConfig(model="claude-3-5-sonnet-20241022")
)

# Direct provider usage
provider = await factory.get_provider("claude")
session = await provider.create_session(query, config)
```

### 2. Streaming Communication
```python
async for response in session.stream_output():
    match response.event_type:
        case StreamEventType.ASSISTANT:
            print(f"Assistant: {response.content}")
        case StreamEventType.TOOL_USE:
            print(f"Tool used: {response.metadata}")
        case StreamEventType.ERROR:
            print(f"Error: {response.content}")
```

### 3. Session Management
```python
# Suspend session
state = await session.suspend()

# Resume later
new_session = await provider.create_session("", session_id=session_id)
await new_session.resume(state)

# Terminate
await session.terminate()
```

## Provider Capabilities

### Claude Provider Capabilities
- ✅ Streaming responses
- ✅ Tool usage (file operations, bash commands)
- ✅ Multimodal input (text, images)
- ✅ Code execution
- ✅ Session continuation
- ✅ Directory change detection
- ✅ Large context windows (200K tokens)

### OpenCode Provider Capabilities
- ✅ Streaming responses
- ✅ Conversation history
- ✅ Multiple model support
- ✅ Cost optimization
- ✅ Long context (up to 2M tokens for Kimi)
- ❌ Tool usage (not yet implemented)
- ❌ File operations
- ❌ Code execution

## Error Handling and Resilience

### Provider-Level Errors
```python
class ProviderError(Exception):
    def __init__(self, message: str, provider: str, session_id: str = None)

class ModelNotSupportedError(ProviderError):
    """Raised when requested model is not available"""

class ProviderUnavailableError(ProviderError): 
    """Raised when provider service is down"""
```

### Session-Level Errors
```python
class SessionError(ProviderError):
    """Session-specific errors with context"""
```

### Automatic Recovery
- Health checks detect provider issues
- Auto-fallback to alternative providers
- Session state preservation during failures
- Graceful degradation of features

## Performance Characteristics

### Claude Provider
- **Session startup**: ~2-3 seconds (subprocess spawn)
- **Response latency**: ~500ms-2s depending on complexity
- **Memory usage**: ~50MB per session (subprocess overhead)
- **Max concurrent sessions**: 10 (configurable)
- **Context retention**: Full conversation history

### OpenCode Provider  
- **Session startup**: ~100ms (API connection)
- **Response latency**: ~200ms-1s depending on model
- **Memory usage**: ~10MB per session (conversation history)
- **Max concurrent sessions**: 20 (configurable)
- **Context retention**: Conversation history only

## Extension Points

### Adding New Providers

1. **Implement Provider Class**:
```python
class MyProvider(BaseProvider):
    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_tools=False,
            max_concurrent_sessions=15
        )
    
    async def create_session(self, query: str, config: SessionConfig) -> MySession:
        # Implementation
        pass
```

2. **Implement Session Class**:
```python
class MySession(BaseSession):
    async def stream_output(self) -> AsyncIterator[StreamResponse]:
        # Implementation
        pass
```

3. **Register Provider**:
```python
from src.jelmore.providers import register_provider
register_provider("myprovider", MyProvider)
```

### Custom Selection Algorithms

The factory supports custom provider selection logic:
```python
async def custom_selector(requirements: Dict[str, Any]) -> Optional[str]:
    # Custom selection logic
    if requirements.get("premium_features"):
        return "claude"
    elif requirements.get("cost_sensitive"):
        return "opencode"
    return None

factory.set_selection_algorithm(custom_selector)
```

## Integration with Existing Systems

### FastAPI Integration
```python
from src.jelmore.providers.factory import initialize_providers

# In FastAPI startup
@app.on_event("startup")
async def startup():
    config = load_provider_config()
    factory = await initialize_providers(get_provider_config_dict(config))
    app.state.provider_factory = factory

# In route handlers
async def create_session(request: SessionRequest):
    factory = request.app.state.provider_factory
    session = await create_session_with_auto_selection(
        query=request.query,
        requirements=request.requirements
    )
    return {"session_id": session.session_id}
```

### Background Tasks
```python
# Session cleanup
@app.on_event("startup")
async def start_cleanup_task():
    async def cleanup_expired_sessions():
        while True:
            for provider in factory.list_active_providers():
                p = await factory.get_provider(provider)
                cleaned = await p.cleanup_expired_sessions()
                logger.info(f"Cleaned {cleaned} expired sessions from {provider}")
            await asyncio.sleep(60)
    
    asyncio.create_task(cleanup_expired_sessions())
```

## Monitoring and Observability

### Health Checks
```python
# Individual provider health
health = await provider.health_check()

# All providers health
health_results = await factory.health_check_all()
```

### Metrics Collection
```python
# Provider metrics
metrics = await factory.get_provider_metrics()
print(f"Total sessions: {metrics['total_sessions']}")
print(f"Active sessions: {metrics['active_sessions']}")

# Individual provider metrics  
provider_metrics = await provider.get_metrics()
```

### Logging Integration
All components use structured logging with consistent fields:
```python
logger.info("Session created", 
           provider="claude",
           session_id=session.session_id,
           model=config.model,
           query_length=len(query))
```

## Security Considerations

### Configuration Security
- API keys loaded from environment variables
- Binary paths validated for existence
- No secrets in configuration files

### Session Isolation
- Each session runs in isolated context
- No cross-session data leakage
- Proper cleanup of sensitive data

### Input Validation
- All inputs validated before processing
- Safe subprocess execution
- Proper error message sanitization

## Future Enhancements

### Planned Features
1. **Model Routing**: Automatic model selection based on query complexity
2. **Caching Layer**: Response caching for common queries
3. **Rate Limiting**: Per-provider and per-user rate limits
4. **A/B Testing**: Split traffic between providers for comparison
5. **Model Fine-tuning**: Integration with custom model training
6. **Multi-modal Support**: Enhanced image and document processing

### Extension APIs
1. **Plugin System**: Loadable provider plugins
2. **Middleware**: Request/response transformation pipeline
3. **Custom Models**: Support for locally hosted models
4. **Provider Chains**: Combine multiple providers for enhanced responses

This architecture provides a solid foundation for AI provider management that can grow with the project's needs while maintaining clean separation of concerns and extensibility.