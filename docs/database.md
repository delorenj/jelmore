# Jelmore Database Schema Documentation

## Overview

Jelmore uses PostgreSQL with SQLAlchemy ORM for managing session and event data. The database is designed to efficiently track long-lived Claude Code sessions and their associated events.

## Schema Design

### Sessions Table

The `sessions` table stores information about Claude Code sessions:

```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    status VARCHAR(50) NOT NULL,  -- SessionStatus enum
    query TEXT NOT NULL,
    claude_process_id VARCHAR(255),
    output_buffer TEXT,
    current_directory VARCHAR(500),
    session_metadata JSONB,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    last_activity TIMESTAMP NOT NULL,
    terminated_at TIMESTAMP
);
```

#### Fields:
- `id`: Unique identifier for the session (UUID)
- `status`: Current session state (INITIALIZING, ACTIVE, IDLE, WAITING_INPUT, TERMINATED, FAILED)
- `query`: The initial query/request that started the session
- `claude_process_id`: Process identifier for the Claude Code instance
- `output_buffer`: Cached output from the session
- `current_directory`: Working directory for the session
- `session_metadata`: Additional metadata as JSON (user_id, project info, etc.)
- `created_at`: Session creation timestamp
- `updated_at`: Last modification timestamp
- `last_activity`: Last activity timestamp
- `terminated_at`: Session termination timestamp (null if active)

### Events Table

The `events` table tracks all activities within sessions:

```sql
CREATE TABLE events (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id),
    event_type VARCHAR(100) NOT NULL,  -- EventType enum
    payload JSONB,
    created_at TIMESTAMP NOT NULL
);
```

#### Fields:
- `id`: Unique identifier for the event (UUID)
- `session_id`: Foreign key reference to the session
- `event_type`: Type of event (see EventType enum below)
- `payload`: Event-specific data as JSON
- `created_at`: Event timestamp

#### Event Types:

**Session Events:**
- `SESSION_CREATED`: Session was created
- `SESSION_STARTED`: Session began execution
- `SESSION_IDLE`: Session became idle
- `SESSION_RESUMED`: Session resumed from idle
- `SESSION_TERMINATED`: Session ended normally
- `SESSION_FAILED`: Session ended with error

**Command Events:**
- `COMMAND_SENT`: Command was sent to Claude Code
- `COMMAND_EXECUTED`: Command completed successfully
- `COMMAND_FAILED`: Command failed

**Output Events:**
- `OUTPUT_RECEIVED`: Output received from Claude Code
- `ERROR_RECEIVED`: Error output received

**Provider Events:**
- `PROVIDER_SWITCHED`: Claude provider was changed
- `PROVIDER_ERROR`: Provider encountered an error

**System Events:**
- `KEEPALIVE`: Periodic health check
- `RESOURCE_WARNING`: Resource usage warning
- `TIMEOUT_WARNING`: Timeout warning

## Indexes

Performance indexes are created on frequently queried columns:

### Sessions Table Indexes:
```sql
CREATE INDEX ix_sessions_status ON sessions(status);
CREATE INDEX ix_sessions_created_at ON sessions(created_at);
CREATE INDEX ix_sessions_last_activity ON sessions(last_activity);
CREATE INDEX ix_sessions_claude_process_id ON sessions(claude_process_id);
```

### Events Table Indexes:
```sql
CREATE INDEX ix_events_session_id ON events(session_id);
CREATE INDEX ix_events_event_type ON events(event_type);
CREATE INDEX ix_events_created_at ON events(created_at);
CREATE INDEX ix_events_session_id_created_at ON events(session_id, created_at);
```

## Connection Configuration

### Connection Pool Settings:
- `pool_size`: 20 connections (configurable via `DATABASE_POOL_SIZE`)
- `max_overflow`: 40 connections (configurable via `DATABASE_MAX_OVERFLOW`)
- `pool_timeout`: 30 seconds
- `pool_recycle`: 3600 seconds (1 hour)

### Environment Variables:
```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=jelmore
POSTGRES_PASSWORD=jelmore_dev
POSTGRES_DB=jelmore
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=40
```

## Migrations

Jelmore uses Alembic for database migrations:

### Create a new migration:
```bash
python -m alembic revision --autogenerate -m "Description of changes"
```

### Apply migrations:
```bash
python -m alembic upgrade head
```

### Rollback migration:
```bash
python -m alembic downgrade -1
```

## Data Types

### Session Status Enum:
```python
class SessionStatus(str, enum.Enum):
    INITIALIZING = "initializing"
    ACTIVE = "active"
    IDLE = "idle"
    WAITING_INPUT = "waiting_input"
    TERMINATED = "terminated"
    FAILED = "failed"
```

### Event Type Enum:
```python
class EventType(str, enum.Enum):
    # Session events
    SESSION_CREATED = "session_created"
    SESSION_STARTED = "session_started"
    # ... (see full enum in models/events.py)
```

## Query Examples

### Get active sessions:
```python
active_sessions = await session.execute(
    select(Session).where(Session.status == SessionStatus.ACTIVE)
)
```

### Get session events:
```python
session_events = await session.execute(
    select(Event)
    .where(Event.session_id == session_id)
    .order_by(Event.created_at)
)
```

### Get recent session activity:
```python
recent_activity = await session.execute(
    select(Session)
    .where(Session.last_activity >= datetime.utcnow() - timedelta(hours=1))
    .order_by(Session.last_activity.desc())
)
```

## Maintenance

### Regular maintenance tasks:
1. **Cleanup old events**: Archive or delete events older than retention period
2. **Monitor connection pool**: Track pool usage and adjust settings if needed
3. **Index maintenance**: Monitor query performance and add indexes as needed
4. **Vacuum and analyze**: Regular PostgreSQL maintenance

### Performance Monitoring:
- Monitor slow queries with `log_min_duration_statement`
- Use `pg_stat_statements` for query analysis
- Track connection pool metrics
- Monitor table growth and partition if necessary

## Backup and Recovery

### Backup strategy:
1. Daily full backups of the database
2. Continuous WAL archiving for point-in-time recovery
3. Regular testing of backup restoration

### Recovery procedures:
1. Point-in-time recovery using WAL files
2. Full database restore from backup
3. Session state recovery from Redis if database is unavailable