# Jelmore - LLM Execution Abstraction Layer

Jelmore is a powerful and flexible LLM execution abstraction layer designed for convention-over-configuration task execution. It provides a dual interface—a comprehensive REST API and a versatile command-line interface (CLI)—for managing and interacting with long-running LLM tasks.

## Features

- **Dual Interface**: A comprehensive REST API for programmatic access and a powerful CLI for interactive use.
- **Multi-Provider Support**: Seamlessly switch between different LLM providers like Claude, OpenAI, and more.
- **Advanced Session Management**: Create, manage, and interact with long-running, persistent LLM sessions.
- **Real-time Streaming**: WebSocket and Server-Sent Events (SSE) for real-time output streaming.
- **Detached Execution**: Run tasks in the background using Zellij for detached, long-running sessions.
- **Comprehensive Monitoring**: Health checks, metrics, and event publishing for robust monitoring.
- **Extensible and Configurable**: Easily extendable to support new providers and highly configurable to fit your workflow.

## Architecture

Jelmore is built on a modern, robust tech stack designed for scalability and performance:

- **Framework**: FastAPI for the asynchronous REST API and Typer for the CLI.
- **Database**: PostgreSQL for persistent storage and Redis for caching and real-time data.
- **Message Bus**: NATS for asynchronous event publishing and inter-service communication.
- **Containerization**: Docker and Docker Compose for easy setup and deployment.

## Getting Started

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- An LLM provider CLI (e.g., Claude CLI) installed and authenticated

### Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/jelmore.git
   cd jelmore
   ```

2. **Run the setup script**:
   ```bash
   ./setup.sh
   ```

3. **Start the infrastructure**:
   ```bash
   docker-compose up -d
   ```

4. **Run database migrations**:
   ```bash
   alembic upgrade head
   ```

5. **Start the API service**:
   ```bash
   uvicorn jelmore.main:app --reload --port 8000
   ```

## Usage

### API

The REST API provides programmatic access to Jelmore's session management features.

#### Endpoints

- `POST /api/v1/sessions`: Create a new session.
- `GET /api/v1/sessions/{session_id}`: Get session details.
- `GET /api/v1/sessions`: List all sessions.
- `DELETE /api/v1/sessions/{session_id}`: Terminate a session.
- `POST /api/v1/sessions/{session_id}/input`: Send input to a waiting session.
- `GET /api/v1/sessions/{session_id}/output`: Get the current session output.
- `GET /api/v1/sessions/{session_id}/stream`: Stream session output via SSE.
- `WS /api/v1/sessions/{session_id}/ws`: Connect to a session via WebSocket.

#### Example: Create a new session

```bash
curl -X POST http://localhost:8000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "query": "Help me create a Python FastAPI application",
    "provider": "claude",
    "model": "claude-3-opus-20240229"
  }'
```

### CLI

The `jelmore` CLI provides a powerful and convenient way to interact with the system from the command line.

#### Commands

- `jelmore execute`: Execute a task with an LLM client.
- `jelmore session`: Manage execution sessions (list, status, attach, logs, kill).
- `jelmore config`: Manage configuration profiles.
- `jelmore status`: Get the status of an execution.

#### Example: Execute a task

```bash
# Simple inline prompt
jelmore execute -p "Fix the login bug" --client claude

# Task from a file with auto context
jelmore execute -f task.md --auto

# Using a pre-configured profile
jelmore execute --profile pr-review
```
