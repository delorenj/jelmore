# Jelmore - Claude Code Session Manager

> FastAPI service that exposes the claude-code SDK to allow spawning personal account token-authenticated long-lived Claude Code sessions via HTTP request.

## Overview

Jelmore is the foundational runtime layer for the 33GOD agentic pipeline system. It provides HTTP API access to Claude Code, enabling programmatic management of AI coding sessions with comprehensive event tracking and state management.

## Features

- 🚀 **Persistent Sessions**: Long-lived Claude Code sessions that stay active until explicitly terminated
- 📊 **Real-time State Tracking**: Monitor session status (active/idle/waiting for input)
- 📁 **Directory Tracking**: Track current working directory and changes
- 🔔 **Event Publishing**: All session events published to NATS for consumption by other services
- 🌊 **Output Streaming**: WebSocket support for real-time output streaming
- 💾 **Dual Storage**: PostgreSQL for persistence + Redis for active state caching
- 🔄 **Session Management**: Create, list, terminate, and send input to sessions

## Tech Stack

- **Framework**: FastAPI (Python 3.12+)
- **Database**: PostgreSQL 16 + Redis 7
- **Message Bus**: NATS 2.10 with JetStream
- **Process Management**: asyncio subprocess
- **Container**: Docker + Docker Compose

## Quick Start

### Prerequisites

- Python 3.12+ (managed via `mise`)
- Docker and Docker Compose
- Claude Code CLI installed and authenticated
- Your Anthropic account with Max plan

### Setup

1. **Clone and navigate to the project**:
```bash
cd /home/delorenj/code/projects/33GOD/jelmore
```

2. **Run the setup script**:
```bash
./setup.sh
```

3. **Start the infrastructure**:
```bash
docker-compose up -d
```

4. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your settings
```

5. **Run database migrations**:
```bash
alembic upgrade head
```

6. **Start the service**:
```bash
uvicorn app.main:app --reload --port 8000
```

## API Endpoints

### Session Management

- `POST /api/v1/session` - Create a new session
- `GET /api/v1/session/{id}` - Get session details
- `GET /api/v1/sessions` - List all sessions
- `DELETE /api/v1/session/{id}` - Terminate a session
- `POST /api/v1/session/{id}/input` - Send input to waiting session
- `WS /api/v1/session/{id}/stream` - Stream session output

### Example Usage

```bash
# Create a new session
curl -X POST http://localhost:8000/api/v1/session \
  -H "Content-Type: application/json" \
  -d '{"query": "Help me create a Python FastAPI application"}'

# Response:
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "active",
  "current_directory": "/home/user/projects",
  "created_at": "2025-08-06T12:00:00",
  "last_activity": "2025-08-06T12:00:01",
  "output_buffer_size": 5
}
```

## Event Schema

All events are published to NATS with the following structure:

```json
{
  "event_type": "session.state_changed",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2025-08-06T12:00:00Z",
  "payload": {
    "from": "active",
    "to": "waiting_input"
  }
}
```

### Event Types

- `session.created` - New session created
- `session.state_changed` - Session state transition
- `session.directory_changed` - Working directory changed
- `session.file_modified` - File system changes detected
- `session.git_activity` - Git operations performed
- `session.terminated` - Session ended

## Development

### Running Tests
```bash
pytest
```

### Code Quality
```bash
black app/
ruff check app/
mypy app/
```

### API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/api/v1/docs
- ReDoc: http://localhost:8000/api/v1/redoc

## Architecture
