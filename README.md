# Jelmore

Unified CLI orchestration layer for multi-provider agentic coding tools.

## Overview

Jelmore provides a single CLI interface to orchestrate multiple AI coding assistants (Claude, Gemini, Codex) with session management, event-driven integration, and extensible hook system.

## Installation

```bash
uv sync
```

## Quick Start

```bash
# Start development environment
mise run dev

# Run the CLI
mise run cli -- --help

# Or directly
uv run jelmore --help
```

## Development

```bash
# Run tests
mise run test

# Run linting
mise run lint

# Run type checking
mise run typecheck

# Run all checks
mise run check
```

## Architecture

- **Command Pattern**: Provider invocations wrapped as Command objects
- **Builder Pattern**: Provider-specific command construction
- **Hook System**: Pre/post execution processing
- **Session Management**: Persistent sessions with continue/resume semantics
- **Event-Driven**: Bloodbank (RabbitMQ) integration for distributed coordination

## License

Private - 33GOD
