## Project Overview

This project, named "Jelmore", is a FastAPI-based service that provides a robust and scalable way to manage long-lived, interactive sessions with the Claude Code AI. It acts as a session manager, exposing the capabilities of the `claude-code` SDK through a comprehensive RESTful API. The system is designed for agentic pipelines, enabling programmatic control over AI coding sessions with features like real-time state tracking, event publishing, and output streaming.

The architecture is built around a set of containerized microservices orchestrated with Docker Compose. The core components include:

- **Jelmore API (FastAPI):** The main application that exposes the REST API and WebSocket endpoints for session management.
- **PostgreSQL:** The primary database for persistent storage of session data.
- **Redis:** Used as a cache for active session state and for real-time data exchange.
- **RabbitMQ:** A messaging system for publishing and subscribing to session events, enabling a decoupled and event-driven architecture.
- **Traefik:** A reverse proxy and load balancer that manages incoming traffic and provides features like SSL termination and rate limiting.

## Building and Running

The project is designed to be run with Docker and Docker Compose. The following commands are used to build and run the application:

- **Build the Docker image:**

  ```bash
  docker-compose build
  ```

- **Start the application and all services:**

  ```bash
  docker-compose up -d
  ```

- **Stop the application and all services:**

  ```bash
  docker-compose down
  ```

- **Run database migrations:**

  ```bash
  alembic upgrade head
  ```

- **Run tests:**
  ```bash
  pytest
  ```

## Development Conventions

The project follows a set of modern Python development conventions:

- **Dependency Management:** Project dependencies are managed with `pyproject.toml`.
- **Code Style:** The codebase is formatted with `black` and `ruff` to ensure a consistent style.
- **Type Checking:** `mypy` is used for static type checking to improve code quality and catch potential errors.
- **Testing:** The project has a comprehensive test suite using `pytest`. Tests are organized into `unit`, `integration`, and `e2e` categories.
- **API Documentation:** The API is documented using the OpenAPI standard, and interactive documentation is available through Swagger UI and ReDoc.
- **Environment Variables:** The application is configured using environment variables, with `.env.example` providing a template for the required variables.
