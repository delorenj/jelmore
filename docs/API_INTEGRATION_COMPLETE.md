# Jelmore Complete API Integration Documentation

## Overview

The Jelmore Complete API Integration (`main_api_integrated.py`) provides a unified FastAPI application that consolidates all session management functionality with comprehensive infrastructure integration.

## Architecture

### Core Components

1. **Session Management API** - RESTful endpoints for session lifecycle
2. **WebSocket Communication** - Real-time bidirectional messaging
3. **Server-Sent Events (SSE)** - One-way streaming for output
4. **Rate Limiting** - Redis-backed distributed rate limiting
5. **Authentication** - API key-based authentication system
6. **Health & Metrics** - Comprehensive monitoring endpoints
7. **Database Integration** - PostgreSQL with Redis caching
8. **Event Bus** - NATS for inter-service communication

### Infrastructure Integration

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI App   │────│  Session Mgmt   │────│   PostgreSQL    │
│  (REST + WS)    │    │     Service     │    │   (Primary)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐              │
         └──────────────│  Redis Cache    │──────────────┘
                        │  (Sessions)     │
                        └─────────────────┘
                                 │
                        ┌─────────────────┐
                        │   NATS Bus      │
                        │   (Events)      │
                        └─────────────────┘
```

## API Endpoints

### Session Management

#### `POST /api/v1/sessions`
Create a new Claude Code session.

**Request:**
```json
{
  "query": "Initial query for Claude Code",
  "user_id": "optional-user-id",
  "current_directory": "/optional/working/directory",
  "metadata": {
    "key": "value"
  },
  "timeout_minutes": 30
}
```

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "initializing",
  "query": "Initial query for Claude Code",
  "current_directory": "/optional/working/directory",
  "user_id": "optional-user-id",
  "claude_process_id": null,
  "metadata": {
    "key": "value"
  },
  "created_at": "2025-08-08T07:15:00.000Z",
  "updated_at": "2025-08-08T07:15:00.000Z",
  "last_activity": "2025-08-08T07:15:00.000Z",
  "terminated_at": null,
  "output_buffer_size": 0
}
```

#### `GET /api/v1/sessions/{session_id}`
Get session details by ID.

**Response:** Same as session creation response with current status.

#### `GET /api/v1/sessions`
List sessions with optional filtering.

**Query Parameters:**
- `user_id`: Filter by user ID
- `status`: Filter by session status
- `limit`: Maximum sessions to return (1-1000, default 100)

**Response:**
```json
[
  {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "active",
    "query": "Initial query",
    ...
  }
]
```

#### `DELETE /api/v1/sessions/{session_id}`
Terminate a session.

**Query Parameters:**
- `reason`: Optional termination reason

**Response:**
```json
{
  "message": "Session terminated successfully",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "reason": "User terminated"
}
```

### Session Interaction

#### `GET /api/v1/sessions/{session_id}/output`
Get current session output buffer.

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "output": "Session output content...",
  "output_length": 1234,
  "status": "active",
  "retrieved_at": "2025-08-08T07:20:00.000Z"
}
```

#### `POST /api/v1/sessions/{session_id}/input`
Send input to a waiting session.

**Request:**
```json
{
  "input": "Command or input text",
  "metadata": {
    "source": "user_input"
  }
}
```

**Response:**
```json
{
  "message": "Input sent successfully",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "input_length": 20
}
```

### Streaming Endpoints

#### `GET /api/v1/sessions/{session_id}/stream`
Server-Sent Events (SSE) stream for session output.

**Headers:**
```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

**Event Types:**
- `connected`: Initial connection established
- `output`: New session output available
- `status`: Session status update
- `terminated`: Session ended
- `error`: Error occurred

**Example Events:**
```
event: connected
data: {"session_id": "550e8400-e29b-41d4-a716-446655440000", "timestamp": "2025-08-08T07:15:00.000Z"}

event: output
data: {"content": "New output text", "timestamp": "2025-08-08T07:15:01.000Z"}

event: status
data: {"status": "active", "timestamp": "2025-08-08T07:15:02.000Z"}
```

#### `WebSocket /api/v1/sessions/{session_id}/ws`
Bidirectional WebSocket communication.

**Incoming Message Types:**
```json
{
  "type": "ping"
}

{
  "type": "input",
  "content": "Command text"
}

{
  "type": "get_status"
}

{
  "type": "subscribe",
  "events": ["output", "status"]
}
```

**Outgoing Event Types:**
```json
{
  "event": "session_info",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "active",
  "timestamp": "2025-08-08T07:15:00.000Z"
}

{
  "event": "output",
  "content": "New output text",
  "timestamp": "2025-08-08T07:15:01.000Z"
}

{
  "event": "pong",
  "timestamp": "2025-08-08T07:15:02.000Z"
}
```

### Monitoring Endpoints

#### `GET /health`
Health check endpoint (no authentication required).

**Response:**
```json
{
  "status": "healthy",
  "service": "jelmore-integrated-api",
  "version": "1.0.0",
  "timestamp": 1725789300.0,
  "infrastructure": {
    "session_service": {
      "status": "healthy",
      "stats": {
        "active_sessions_count": 5,
        "service_running": true
      }
    },
    "websocket_manager": {
      "status": "healthy",
      "stats": {
        "total_connections": 3,
        "sessions_with_connections": 2
      }
    }
  }
}
```

#### `GET /metrics`
Prometheus metrics endpoint (no authentication required).

**Response:** Prometheus-formatted metrics or 503 if not available.

#### `GET /api/v1/stats`
System statistics endpoint (requires authentication).

**Response:**
```json
{
  "service": "jelmore-integrated-api",
  "version": "1.0.0",
  "timestamp": 1725789300.0,
  "uptime_seconds": 3600,
  "session_stats": {
    "active_sessions_count": 5,
    "service_running": true,
    "monitoring_interval_seconds": 30,
    "cleanup_interval_seconds": 300
  },
  "websocket_stats": {
    "total_connections": 3,
    "sessions_with_connections": 2,
    "manager_running": true
  },
  "settings": {
    "max_concurrent_sessions": 100,
    "session_timeout_seconds": 3600,
    "cleanup_interval_seconds": 300,
    "api_prefix": "/api",
    "cors_origins": ["*"]
  }
}
```

## Authentication

All API endpoints (except `/health` and `/metrics`) require API key authentication.

### Headers
```
Authorization: Bearer YOUR_API_KEY
```

### Error Responses
```json
{
  "detail": "Invalid API key"
}
```

## Rate Limiting

The API implements comprehensive rate limiting:

### Rate Limit Headers
All responses include rate limiting information:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1725792900
X-RateLimit-Window: 3600
```

### Rate Limit Rules
- **Global**: 1000 requests per hour
- **Authentication**: 10 requests per minute
- **Session Creation**: 20 requests per minute
- **Streaming**: 5 requests per minute
- **WebSocket**: 10 connections per minute

### Rate Limit Exceeded Response
```json
{
  "error": "Rate limit exceeded",
  "message": "Too many requests: 20 per 60 seconds",
  "limit": 20,
  "window_seconds": 60,
  "retry_after": 45,
  "remaining": 0
}
```

## Error Handling

### Standard Error Response Format
```json
{
  "detail": "Error description",
  "error_code": "OPTIONAL_ERROR_CODE",
  "timestamp": "2025-08-08T07:15:00.000Z"
}
```

### HTTP Status Codes
- `200`: Success
- `201`: Created
- `400`: Bad Request (validation errors)
- `401`: Unauthorized (authentication required)
- `403`: Forbidden (insufficient permissions)
- `404`: Not Found
- `422`: Unprocessable Entity (validation errors)
- `429`: Too Many Requests (rate limited)
- `500`: Internal Server Error
- `503`: Service Unavailable

## WebSocket Connection Management

### Connection Lifecycle
1. **Connect**: `WebSocket /api/v1/sessions/{session_id}/ws`
2. **Authentication**: Verified through session existence
3. **Initial Message**: Server sends session info
4. **Bidirectional Communication**: Real-time messaging
5. **Heartbeat**: Automatic ping/pong for connection health
6. **Cleanup**: Automatic disconnection on session termination

### Message Protocol
All WebSocket messages are JSON formatted:

```json
{
  "event": "event_type",
  "timestamp": "2025-08-08T07:15:00.000Z",
  "data": { }
}
```

### Connection States
- **Connected**: Active bidirectional communication
- **Streaming**: Receiving session output
- **Waiting**: Idle, waiting for messages
- **Disconnected**: Connection closed

## Server-Sent Events (SSE)

### Connection Setup
```javascript
const eventSource = new EventSource('/api/v1/sessions/SESSION_ID/stream', {
  headers: {
    'Authorization': 'Bearer YOUR_API_KEY'
  }
});

eventSource.addEventListener('output', (event) => {
  const data = JSON.parse(event.data);
  console.log('New output:', data.content);
});

eventSource.addEventListener('status', (event) => {
  const data = JSON.parse(event.data);
  console.log('Status update:', data.status);
});

eventSource.addEventListener('error', (event) => {
  console.error('SSE error:', event.data);
});
```

### Event Stream Format
```
event: connected
data: {"session_id": "550e8400-e29b-41d4-a716-446655440000", "timestamp": "2025-08-08T07:15:00.000Z"}

event: output
data: {"content": "Command output text", "timestamp": "2025-08-08T07:15:01.000Z"}
```

## Infrastructure Integration

### Database Layer
- **Primary Storage**: PostgreSQL for session persistence
- **Caching Layer**: Redis for fast session access
- **Write-Through**: Updates written to both PostgreSQL and Redis
- **Cache Recovery**: Automatic Redis repopulation from PostgreSQL

### Event Bus Integration
- **NATS JetStream**: Reliable event streaming
- **Event Types**: Session lifecycle, status changes, commands
- **Consumer Groups**: Horizontal scaling support
- **Event Replay**: Historical event access

### Session Lifecycle Events
```json
{
  "event_type": "session.created",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "payload": {
    "query": "Initial query",
    "user_id": "user-123",
    "created_by": "api-key-name"
  },
  "timestamp": "2025-08-08T07:15:00.000Z"
}
```

### Monitoring and Observability
- **Structured Logging**: JSON-formatted logs with correlation IDs
- **Prometheus Metrics**: Request counts, durations, active sessions
- **Health Checks**: Comprehensive infrastructure status
- **Error Tracking**: Detailed error context and stack traces

## Deployment Configuration

### Environment Variables
```bash
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_PREFIX=/api
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/jelmore
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# Redis
REDIS_URL=redis://localhost:6379/0

# NATS
NATS_URL=nats://localhost:4222

# Authentication
API_KEYS={"admin": {"permissions": ["admin"]}, "user": {"permissions": ["read", "write"]}}

# Session Management
MAX_CONCURRENT_SESSIONS=100
SESSION_DEFAULT_TIMEOUT_SECONDS=3600
SESSION_CLEANUP_INTERVAL_SECONDS=300
SESSION_MONITORING_INTERVAL_SECONDS=30

# CORS
CORS_ORIGINS=["*"]
```

### Docker Compose Integration
```yaml
version: '3.8'
services:
  jelmore-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:password@postgres:5432/jelmore
      - REDIS_URL=redis://redis:6379/0
      - NATS_URL=nats://nats:4222
    depends_on:
      - postgres
      - redis
      - nats
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Kubernetes Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: jelmore-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: jelmore-api
  template:
    spec:
      containers:
      - name: api
        image: jelmore:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: jelmore-secrets
              key: database-url
        healthcheck:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
```

## Testing

### Integration Tests
Run comprehensive integration tests:
```bash
pytest tests/integration/test_complete_api_integration.py -v
```

### Load Testing
```bash
# Install artillery
npm install -g artillery

# Run load test
artillery run tests/load/api-load-test.yml
```

### Manual Testing
```bash
# Health check
curl http://localhost:8000/health

# Create session
curl -X POST http://localhost:8000/api/v1/sessions \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"query": "Test query", "user_id": "test-user"}'

# Stream output (SSE)
curl -N http://localhost:8000/api/v1/sessions/SESSION_ID/stream \\
  -H "Authorization: Bearer YOUR_API_KEY"
```

## Performance Considerations

### Optimization Features
- **Connection Pooling**: Database and Redis connection pools
- **Async Operations**: Full async/await throughout
- **Caching Strategy**: Redis write-through caching
- **Rate Limiting**: Distributed rate limiting with Redis
- **Event Streaming**: Efficient NATS JetStream integration

### Scalability
- **Horizontal Scaling**: Stateless API design
- **Load Balancing**: Multiple API instances supported
- **Database Sharding**: Session data can be partitioned
- **Caching Layer**: Redis cluster support
- **Event Bus**: NATS clustering for high availability

### Monitoring
- **Prometheus Metrics**: Request latency, error rates, active sessions
- **Health Checks**: Infrastructure component status
- **Structured Logs**: JSON-formatted with correlation IDs
- **Error Tracking**: Comprehensive error context

## Security Considerations

### Authentication & Authorization
- **API Key Management**: Secure key storage and rotation
- **Permission System**: Role-based access control
- **Rate Limiting**: DoS protection and fair usage
- **Input Validation**: Comprehensive request validation

### Data Protection
- **Session Isolation**: User data separation
- **Secure Communication**: HTTPS/WSS in production
- **Credential Management**: Environment-based secrets
- **Audit Logging**: All actions logged with user context

### Infrastructure Security
- **Network Isolation**: Service-to-service communication
- **Database Security**: Connection encryption and access controls
- **Cache Security**: Redis AUTH and network restrictions
- **Event Bus Security**: NATS authentication and authorization

## Troubleshooting

### Common Issues

#### WebSocket Connection Failures
```bash
# Check session exists
curl http://localhost:8000/api/v1/sessions/SESSION_ID \\
  -H "Authorization: Bearer YOUR_API_KEY"

# Check WebSocket manager status
curl http://localhost:8000/api/v1/stats \\
  -H "Authorization: Bearer YOUR_API_KEY"
```

#### Rate Limiting Issues
Check rate limit headers in responses:
```bash
curl -I http://localhost:8000/api/v1/sessions \\
  -H "Authorization: Bearer YOUR_API_KEY"
```

#### Database Connection Issues
```bash
# Check health endpoint
curl http://localhost:8000/health

# Check database stats
curl http://localhost:8000/api/v1/stats \\
  -H "Authorization: Bearer YOUR_API_KEY"
```

### Logs Analysis
```bash
# API logs
docker logs jelmore-api

# Database connection logs
grep "database" /var/log/jelmore/app.log

# WebSocket connection logs
grep "websocket" /var/log/jelmore/app.log
```

### Performance Debugging
```bash
# Check active sessions
curl http://localhost:8000/api/v1/stats \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  | jq .session_stats

# Monitor Prometheus metrics
curl http://localhost:8000/metrics
```

## API Client Examples

### Python Client
```python
import httpx
import asyncio
import json

class JelmoreClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {api_key}"}
    
    async def create_session(self, query: str, user_id: str = None):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/sessions",
                headers=self.headers,
                json={"query": query, "user_id": user_id}
            )
            response.raise_for_status()
            return response.json()
    
    async def stream_output(self, session_id: str):
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "GET",
                f"{self.base_url}/api/v1/sessions/{session_id}/stream",
                headers=self.headers
            ) as stream:
                async for chunk in stream.aiter_text():
                    if chunk.strip():
                        yield chunk.strip()

# Usage
async def main():
    client = JelmoreClient("http://localhost:8000", "your-api-key")
    
    # Create session
    session = await client.create_session("List files in current directory")
    session_id = session["session_id"]
    
    # Stream output
    async for event in client.stream_output(session_id):
        if "event: output" in event:
            print(f"Output: {event}")

asyncio.run(main())
```

### JavaScript Client
```javascript
class JelmoreClient {
  constructor(baseUrl, apiKey) {
    this.baseUrl = baseUrl;
    this.headers = { 'Authorization': `Bearer ${apiKey}` };
  }
  
  async createSession(query, userId = null) {
    const response = await fetch(`${this.baseUrl}/api/v1/sessions`, {
      method: 'POST',
      headers: { ...this.headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, user_id: userId })
    });
    
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }
  
  streamOutput(sessionId, onOutput, onStatus, onError) {
    const eventSource = new EventSource(
      `${this.baseUrl}/api/v1/sessions/${sessionId}/stream`,
      { headers: this.headers }
    );
    
    eventSource.addEventListener('output', (event) => {
      const data = JSON.parse(event.data);
      onOutput(data.content);
    });
    
    eventSource.addEventListener('status', (event) => {
      const data = JSON.parse(event.data);
      onStatus(data.status);
    });
    
    eventSource.addEventListener('error', (event) => {
      onError(event.data);
    });
    
    return eventSource;
  }
  
  connectWebSocket(sessionId, onMessage) {
    const ws = new WebSocket(`ws://localhost:8000/api/v1/sessions/${sessionId}/ws`);
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      onMessage(data);
    };
    
    ws.sendInput = (input) => {
      ws.send(JSON.stringify({ type: 'input', content: input }));
    };
    
    return ws;
  }
}

// Usage
const client = new JelmoreClient('http://localhost:8000', 'your-api-key');

// Create session and stream output
client.createSession('Help me with Python coding')
  .then(session => {
    console.log('Session created:', session.session_id);
    
    // Stream output
    client.streamOutput(
      session.session_id,
      (output) => console.log('Output:', output),
      (status) => console.log('Status:', status),
      (error) => console.error('Error:', error)
    );
  });
```

---

This documentation provides comprehensive coverage of the Jelmore Complete API Integration, including all endpoints, authentication, real-time features, infrastructure integration, deployment considerations, and client examples.