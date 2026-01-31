# Technical Specification: Jelmore

**Project:** Jelmore
**Type:** API/CLI Tool (Event-Driven Orchestration Layer)
**Level:** 1 (Small - 1-10 stories)
**Date:** 2026-01-27
**Status:** Draft
**Version:** 1.0

---

## 1. Problem & Solution

### Problem Statement

Developers working with multiple agentic coding tools (Claude Code, Gemini CLI, Codex) need a unified orchestration layer that can be triggered programmatically through event-driven workflows. Current tools require direct CLI invocation and lack event emission for observability and coordination within broader automation pipelines. Additionally, there's no unified way to manage sessions or search across conversation histories from different providers.

### Proposed Solution

Jelmore acts as an event-driven orchestration layer for agentic coders. It listens for Bloodbank commands to launch provider sessions and emits Bloodbank events at key execution points (tool calls, thinking, responses). The system provides:

- **Dual Interface:** Bloodbank event consumption (primary) + CLI interface (development/testing)
- **Provider Abstraction:** Factory pattern with specialized builders for each provider (Claude, Gemini, Codex)
- **Command Pattern:** Chainable command objects for multi-step workflows (ordered/parallel execution)
- **Observability:** Event emission at critical execution points with correlation ID tracing
- **Session Management:** Unified session storage, continue vs resume semantics, cross-provider search
- **Resilience:** Retry logic with exponential backoff, DLQ routing, hook system for extensibility

This enables programmatic control, observability, and integration with other 33GOD components while maintaining clean architectural boundaries.

---

## 2. Requirements

### Functional Requirements

1. **Provider Abstraction Layer**
   - Factory pattern creates provider-specific command builders (Claude, Gemini, Codex)
   - Common interface for all providers with specialized implementations
   - Easy extensibility for adding new providers (OpenCode, Copilot CLI, Auggie, Kimmy)

2. **Event-Driven Command System**
   - Bloodbank listener consumes `agent.prompt` events
   - Parse payload and build commands via Factory
   - Execute with retry logic (3x exponential backoff: 1s, 2s, 4s)
   - Emit results to Bloodbank with correlation ID

3. **CLI Interface**
   - Direct command invocation for dev/testing
   - Translates to same command structure as event-driven path
   - Commands: `start`, `sessions list/search/resume`, `config show/set/validate`, `listen`
   - Unified parameter interface across providers

4. **Command Chaining**
   - Chainable command objects for multi-step workflows
   - Support ordered (sequential) and parallel execution modes
   - Optional response passing between chained commands

5. **Hook System**
   - Pre/post execution hooks (auth, validation, logging)
   - Hooks defined inline in payload or imposed by builder
   - Hook ordering and execution guarantees

6. **Session Management**
   - Persist session state to Redis + XDG_CONFIG_HOME backup
   - Support continue (resume current) and resume (select from list) semantics
   - Session metadata includes correlation IDs for tracing
   - CRUD operations: create, read, update, list

7. **Cross-Provider Session Search**
   - Search and query across all provider session histories
   - Full-text search on prompts, responses, metadata
   - Filter by provider, date range, correlation ID

8. **Side Effect Processing**
   - Queue side effects during execution
   - Command side effects emit to Bloodbank with correlation ID
   - Response side effects packaged for fanout
   - Side effects processed in order

9. **Observability**
   - Emit Bloodbank events at: tool calls, thinking, responses
   - Structured logging with correlation IDs (structlog)
   - Failures routed to DLQ with full context
   - Execution metrics and timing

10. **Configuration Management**
    - YAML config in `~/.config/jelmore/config.yaml`
    - Pydantic validation on startup
    - Environment variable overrides
    - Provider-specific settings

### Out of Scope (Initial Implementation)

- Additional providers beyond Claude, Gemini, Codex (deferred to future iterations)
- Web UI for session browsing and management
- Multi-user support and authentication
- Advanced workflow orchestration (conditional branching, loops)
- Real-time session streaming/visualization
- Provider-specific feature utilization (beyond basic prompting)
- Cross-platform support (macOS, Windows)
- Advanced search (semantic search, embeddings)

---

## 3. Technical Approach

### Technology Stack

```yaml
Language/Framework: Python 3.11+ with uv for dependency management
Event Bus: RabbitMQ (Bloodbank) for event consumption/emission
Session Storage: Redis for session state + metadata persistence
Data Validation: Pydantic for strict typing on commands/payloads
CLI Framework: Click or Typer for CLI interface
Logging: structlog for structured logging with correlation IDs
Testing: pytest with pytest-asyncio
Configuration: YAML config files in XDG_CONFIG_HOME (~/.config/jelmore/)
Containerization: Docker + docker-compose for development
Task Runner: mise tasks for common operations
Credential Management: 1Password CLI (op read) for provider API keys
```

### Architecture Overview

**Component Structure:**

```
jelmore/
├── cli/               # CLI entrypoint (Click/Typer commands)
│   ├── __init__.py
│   ├── main.py       # Main CLI app
│   ├── start.py      # Start command
│   ├── sessions.py   # Session commands
│   └── config.py     # Config commands
├── listeners/         # Bloodbank event listeners
│   └── agent_prompt_listener.py
├── commands/          # Command pattern implementation
│   ├── base.py       # Abstract Command interface
│   ├── claude.py     # Claude-specific command
│   ├── gemini.py     # Gemini-specific command
│   └── codex.py      # Codex-specific command
├── builders/          # Command builders (Factory pattern)
│   ├── factory.py    # Main factory for builder selection
│   ├── claude_builder.py
│   ├── gemini_builder.py
│   └── codex_builder.py
├── executor/          # Command execution engine
│   ├── executor.py   # Orchestrates command chains
│   └── retry.py      # Retry logic with backoff
├── hooks/             # Pre/post execution hooks
│   ├── base.py       # Hook interface
│   ├── auth.py       # Authentication hook
│   └── logging.py    # Logging hook
├── session/           # Session management
│   ├── manager.py    # Session CRUD operations
│   ├── storage.py    # Redis persistence layer
│   └── search.py     # Cross-provider search
├── events/            # Bloodbank event handling
│   ├── producer.py   # Event emission
│   └── consumer.py   # Event consumption
├── models/            # Pydantic models
│   ├── commands.py   # Command payloads
│   ├── sessions.py   # Session data structures
│   └── events.py     # Event schemas
└── providers/         # Provider-specific adapters
    ├── base.py       # Provider interface
    ├── claude.py     # Claude Code integration
    ├── gemini.py     # Gemini CLI integration
    └── codex.py      # Codex integration
```

**Execution Flow:**

```
Input (Bloodbank event or CLI)
  ↓
AgentPromptCommandBuilder (Factory)
  ↓ (specialization based on provider)
ClaudeCommandBuilder | GeminiCommandBuilder | CodexCommandBuilder
  ↓ (DI injects context)
Concrete Command Instance
  ↓ (hook attachment)
Pre/Post Hooks (auth, validation, logging)
  ↓ (chaining)
Ordered/Parallel Command Chain
  ↓
Executor
  ├─ Retry loop (3x, exponential backoff: 1s, 2s, 4s)
  ├─ Invoke: await cmd.invoke(previous_response?)
  ├─ Side Effect Queue (commands + responses)
  └─ On failure → DLQ
  ↓
Side Effect Processing
  ├─ Command side effect → emit to Bloodbank (correlation_id)
  └─ Response side effect → package & fanout
```

### CLI Interface Design

```bash
# Launch provider session
jelmore start <provider> [options]
  --prompt TEXT          Initial prompt to send
  --session-id TEXT      Resume specific session
  --continue             Continue last session
  --config FILE          Use custom config file

# Session management
jelmore sessions list [provider]
  --limit INT            Number of sessions to show
  --format [table|json]  Output format

jelmore sessions search <query>
  --provider TEXT        Filter by provider
  --date-range TEXT      Filter by date range

jelmore sessions resume <session-id>

# Configuration
jelmore config show
jelmore config set <key> <value>
jelmore config validate

# Event-driven mode (daemon)
jelmore listen
  --queue TEXT           Bloodbank queue name
  --workers INT          Number of worker threads
```

### Data Model

**Core Pydantic Models:**

```python
# Command Payload
class AgentPromptPayload(BaseModel):
    provider: Literal["claude", "gemini", "codex"]
    prompt: str
    session_id: Optional[str] = None
    continuation_mode: Literal["new", "continue", "resume"] = "new"
    hooks: Optional[List[HookConfig]] = None
    metadata: Dict[str, Any] = {}
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))

# Session Data
class Session(BaseModel):
    id: str
    provider: str
    created_at: datetime
    updated_at: datetime
    state: Dict[str, Any]  # Provider-specific state
    metadata: Dict[str, Any]
    correlation_ids: List[str]  # For tracing command chains

# Command Result
class CommandResult(BaseModel):
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    side_effects: List[SideEffect] = []
    execution_time: float
    correlation_id: str

# Side Effect
class SideEffect(BaseModel):
    type: Literal["command", "response"]
    payload: Dict[str, Any]
    correlation_id: str
    parent_correlation_id: str
```

**Redis Schema:**

```
# Session storage
sessions:{provider}:{session_id} -> JSON(Session)

# Indexing
session:index:{provider} -> Sorted Set (by timestamp)

# Search
session:search:tokens -> Inverted index for full-text search

# Tracing
correlation:{correlation_id} -> List of linked session/command IDs
```

---

## 4. Implementation Plan

### Story Breakdown (10 Stories)

**1. Foundation & Project Structure**
- Set up Python project with uv
- Define base abstractions (Command, Builder, Provider interfaces)
- Pydantic models for core entities
- Configuration system (XDG_CONFIG_HOME)
- Docker setup with Redis + RabbitMQ
- mise tasks for common operations

**2. Command System Core**
- Implement Command pattern with base Command class
- Factory for builder selection
- Concrete ClaudeCommandBuilder
- Command chaining logic (ordered/parallel)
- Basic execution without retry

**3. Provider Integration (Claude)**
- Complete Claude provider adapter
- End-to-end flow: CLI → Command → Claude Code invocation
- Session state capture
- Basic success/failure handling
- Validates architecture with one working provider

**4. Session Management**
- Redis-backed session storage
- CRUD operations (create, read, update, list)
- Session metadata with correlation IDs
- Continue vs resume logic
- Persistence to XDG_CONFIG_HOME for local backup

**5. Event-Driven System**
- Bloodbank consumer listening to agent.prompt queue
- Event payload parsing
- Integration with command builder factory
- Bloodbank producer for result emission
- Correlation ID propagation

**6. CLI Interface**
- Click/Typer commands: `start`, `sessions`, `config`
- Human-friendly output formatting
- CLI translates to command system (same path as events)
- Config validation and display

**7. Executor & Retry Logic**
- Command executor with retry loop (3x exponential backoff)
- Side effect queue during execution
- Failure handling with DLQ routing
- Execution metrics and timing

**8. Hook System**
- Hook interface (pre/post)
- Auth hook implementation
- Logging hook implementation
- Hook attachment (inline payload + builder-imposed)
- Hook ordering and execution

**9. Cross-Provider Session Search**
- Full-text search indexing (Redis inverted index)
- Search across all providers
- Query by prompt/response content
- Metadata filtering (date range, provider)

**10. Additional Providers & Observability**
- Gemini provider implementation
- Codex provider implementation
- Event emission at tool calls/thinking/responses
- Structured logging with correlation IDs
- Complete documentation

### Development Phases

**Phase 1 (Foundation):** Stories 1, 2
**Phase 2 (First Provider):** Stories 3, 4
**Phase 3 (Event Integration):** Stories 5, 6
**Phase 4 (Resilience):** Stories 7, 8
**Phase 5 (Search & Scale):** Stories 9, 10

---

## 5. Acceptance Criteria

### Core Functionality
- [ ] Can invoke Claude Code via CLI with `jelmore start claude --prompt "..."`
- [ ] Can invoke Claude Code via Bloodbank agent.prompt event
- [ ] Sessions persist to Redis with correlation IDs
- [ ] Can continue last session with `jelmore start claude --continue`
- [ ] Can resume specific session with `jelmore sessions resume <id>`
- [ ] CLI and event-driven paths produce identical command execution

### Session Management
- [ ] Sessions list correctly for all providers
- [ ] Cross-provider search finds sessions by prompt content
- [ ] Session metadata includes correlation IDs for tracing
- [ ] Config stored in `~/.config/jelmore/config.yaml`
- [ ] Session data backed up to XDG_CONFIG_HOME

### Event System
- [ ] Bloodbank listener consumes agent.prompt queue
- [ ] Command results emit to Bloodbank with correlation ID
- [ ] Side effects (commands/responses) processed in order
- [ ] Tool call, thinking, and response events emitted during execution

### Resilience
- [ ] Failed commands retry 3x with exponential backoff (1s, 2s, 4s)
- [ ] Failures after retry route to DLQ
- [ ] Hook system allows pre/post execution hooks
- [ ] Auth hook validates before execution

### Architecture
- [ ] Factory pattern correctly routes to provider builders
- [ ] Command chaining works for ordered execution
- [ ] Provider interface allows easy addition of new providers
- [ ] All components use Pydantic for strict typing

### Testing & Observability
- [ ] Unit tests cover command system, builders, session management
- [ ] Integration test: CLI → Command → Claude execution → Session stored
- [ ] Integration test: Bloodbank event → Command → Result emitted
- [ ] Structured logs include correlation IDs
- [ ] Docker compose brings up full local environment

### Documentation
- [ ] README covers installation, configuration, usage examples
- [ ] Architecture diagram shows component interactions
- [ ] Provider integration guide for adding new providers

---

## 6. Non-Functional Requirements

### Performance
- Command orchestration overhead: < 500ms (provider execution time is separate)
- Concurrent event processing: 5 workers initially, configurable
- Session search latency: < 1s for typical queries (< 1000 sessions)
- Retry backoff: Exponential (1s, 2s, 4s) with 4s max wait between attempts

### Security
- Provider API keys: Environment variables or 1Password CLI integration (`op read`)
- Bloodbank auth: Internal 33GOD infrastructure, no auth initially (trusted network)
- Session data: Rely on Redis ACLs and network security, no application-level encryption for v1
- Credential storage: 1Password CLI for sensitive provider credentials

### Other
- **Platform:** Linux only (development/server environments)
- **Logging:** Verbose structured logs via structlog, 30-day retention, Candystore receives all events
- **Graceful Degradation:** Fail fast on startup if Redis/RabbitMQ unavailable (development tool, not production service)
- **Config Validation:** Pydantic validation on startup, fail with clear error messages
- **Docker Health Checks:** Redis, RabbitMQ containers report healthy before Jelmore starts

---

## 7. Dependencies, Risks, Timeline

### Dependencies

**External Services:**
- Bloodbank (RabbitMQ) - must be running and accessible
- Redis - for session storage
- Provider CLIs - Claude Code, Gemini CLI, Codex must be installed
- Candystore (optional) - for event storage if integrated

**Internal Dependencies:**
- 33GOD infrastructure (Bloodbank connection details, queue names)
- 1Password CLI (for credential management)

**Development Dependencies:**
- Docker + docker-compose
- Python 3.11+
- uv package manager
- mise for task running

### Risks & Mitigations

**Risk 1: Provider CLI API Changes**
- **Impact:** Provider-specific adapters break when CLI interfaces change
- **Mitigation:** Abstract provider interface, version pinning, comprehensive integration tests

**Risk 2: Event Message Format Evolution**
- **Impact:** Breaking changes to agent.prompt payload schema
- **Mitigation:** Pydantic schema versioning, backward-compatible parsing, validation errors fail gracefully

**Risk 3: Session State Corruption**
- **Impact:** Redis data becomes inconsistent or corrupted
- **Mitigation:** XDG_CONFIG_HOME backup, Redis persistence (AOF), session validation on load

**Risk 4: Command Chain Complexity**
- **Impact:** Chained commands become hard to debug, side effects cascade unexpectedly
- **Mitigation:** Correlation ID tracing, verbose structured logging, command execution visualization

**Risk 5: Retry Logic Resource Exhaustion**
- **Impact:** Failed commands retry indefinitely, consume resources
- **Mitigation:** Hard limit of 3 retries, exponential backoff, DLQ routing after max attempts

### Timeline

**Target Completion:** ASAP

**Milestones:**
1. **Foundation Complete** - Project scaffolding, base interfaces, Docker environment working
2. **First Provider Working** - Claude Code invocable via CLI, sessions persisting
3. **Event System Live** - Bloodbank listener consuming events, emitting results
4. **Feature Complete** - All 10 stories implemented, acceptance criteria met
5. **Production Ready** - Tests passing, documentation complete, deployed

---

## Appendix

### Key Design Patterns

- **Factory Pattern:** Builder selection based on provider type
- **Command Pattern:** Encapsulates provider invocations as objects
- **Chain of Responsibility:** Hook system for pre/post processing
- **Strategy Pattern:** Provider-specific adapters implement common interface

### Future Enhancements (Post-v1)

- Additional providers: OpenCode, Copilot CLI, Auggie, Kimmy
- Web UI for session management and visualization
- Advanced workflow orchestration (conditionals, loops)
- Semantic search with embeddings
- Multi-user support with RBAC
- Real-time session streaming
- Provider-specific feature utilization (tool use, context management)
- Cross-platform support (macOS, Windows)

### References

- 33GOD Architecture: Bloodbank event bus, Candystore event storage
- Gang of Four Patterns: Creational, Behavioral, Structural patterns
- Kickoff Notes: `/home/delorenj/code/33GOD/jelmore/trunk-main/docs/kickoff.md`
