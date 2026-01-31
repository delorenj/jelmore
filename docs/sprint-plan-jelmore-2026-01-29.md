# Sprint Plan: Jelmore

**Date:** 2026-01-29
**Scrum Master:** Jarad DeLorenzo
**Project Level:** 1 (1-10 stories)
**Total Stories:** 10
**Total Points:** 59
**Planned Sprints:** 2
**Plane Project:** 33god/jelmore

---

## Executive Summary

Jelmore is an event-driven orchestration layer for agentic coders (Claude Code, Gemini CLI, Codex). This sprint plan breaks the technical specification into 10 implementation stories across 2 sprints, prioritizing foundational infrastructure and the Claude provider integration first.

**Key Metrics:**
- Total Stories: 10
- Total Points: 59
- Sprints: 2
- Team Capacity: ~30 points per sprint
- Target Completion: 4 weeks

---

## Story Inventory

### STORY-001: Foundation & Project Structure

**Priority:** must-have
**Points:** 5 (effort:M)
**Type:** infrastructure

**User Story:**
As a developer
I want a properly structured Python project with all dependencies and tooling configured
So that I can begin implementing features immediately

**Acceptance Criteria:**
- [ ] Python project initialized with uv
- [ ] Base abstractions defined (Command, Builder, Provider interfaces)
- [ ] Pydantic models for core entities (AgentPromptPayload, Session, CommandResult, SideEffect)
- [ ] Configuration system using XDG_CONFIG_HOME (~/.config/jelmore/)
- [ ] Docker setup with Redis + RabbitMQ containers
- [ ] mise tasks for common operations (dev, test, lint, docker:up, docker:down)
- [ ] .env.example with all required environment variables
- [ ] pyproject.toml with all dependencies

**Technical Notes:**
- Use uv for fast dependency management
- structlog for logging, pydantic for validation
- Docker compose for local development services
- mise tasks should wrap common developer workflows

**Dependencies:** None (first story)

---

### STORY-002: Command System Core

**Priority:** must-have
**Points:** 5 (effort:M)
**Type:** feature

**User Story:**
As a developer
I want a command pattern implementation with factory-based builder selection
So that I can execute provider commands through a consistent interface

**Acceptance Criteria:**
- [ ] Abstract Command class with invoke() method
- [ ] Factory class for builder selection based on provider type
- [ ] ClaudeCommandBuilder implementation
- [ ] Command chaining logic (ordered execution)
- [ ] Basic execution without retry (happy path)
- [ ] Unit tests for command creation and chaining

**Technical Notes:**
- Follow Gang of Four Command pattern
- Factory returns appropriate builder based on provider string
- Commands are chainable via fluent interface or explicit chain()
- Each command has pre/post hook attachment points

**Dependencies:** STORY-001

---

### STORY-003: Claude Provider Integration

**Priority:** must-have
**Points:** 8 (effort:XL)
**Type:** feature

**User Story:**
As a user
I want to invoke Claude Code through Jelmore
So that I can programmatically control Claude Code sessions

**Acceptance Criteria:**
- [ ] Claude provider adapter implementing Provider interface
- [ ] End-to-end flow: CLI → Command → Claude Code invocation
- [ ] Session state capture from Claude Code output
- [ ] Basic success/failure handling
- [ ] Integration test with actual Claude Code invocation
- [ ] Provider configuration (model, max tokens, etc.)

**Technical Notes:**
- Claude Code is invoked via subprocess
- Parse stdout/stderr for response content
- Capture session ID from Claude Code for resume capability
- Handle common failure modes (auth, rate limits, network)

**Dependencies:** STORY-001, STORY-002

---

### STORY-004: Session Management

**Priority:** must-have
**Points:** 5 (effort:M)
**Type:** feature

**User Story:**
As a user
I want my sessions to persist across invocations
So that I can continue or resume previous conversations

**Acceptance Criteria:**
- [ ] Redis-backed session storage (SessionStorage class)
- [ ] CRUD operations: create, read, update, list
- [ ] Session metadata with correlation IDs
- [ ] Continue logic (resume most recent session for provider)
- [ ] Resume logic (select specific session by ID)
- [ ] Local backup to XDG_CONFIG_HOME for offline access
- [ ] Unit tests for session CRUD operations

**Technical Notes:**
- Redis keys: sessions:{provider}:{session_id}
- Index by provider: session:index:{provider} (sorted set by timestamp)
- JSON serialization for session state
- Background sync to local YAML files

**Dependencies:** STORY-001

---

### STORY-005: Event-Driven System

**Priority:** must-have
**Points:** 8 (effort:XL)
**Type:** feature

**User Story:**
As a system integrator
I want Jelmore to consume and emit Bloodbank events
So that it integrates with the 33GOD automation ecosystem

**Acceptance Criteria:**
- [ ] Bloodbank consumer listening to agent.prompt queue
- [ ] Event payload parsing into AgentPromptPayload
- [ ] Integration with command builder factory
- [ ] Bloodbank producer for result emission
- [ ] Correlation ID propagation through entire flow
- [ ] Integration test: event in → command executed → result emitted
- [ ] Graceful handling of malformed events

**Technical Notes:**
- Use pika or aio-pika for RabbitMQ
- agent.prompt queue for incoming commands
- agent.response queue for outgoing results
- agent.error queue for failures
- All events include correlation_id for tracing

**Dependencies:** STORY-001, STORY-002, STORY-003

---

### STORY-006: CLI Interface

**Priority:** should-have
**Points:** 5 (effort:M)
**Type:** feature

**User Story:**
As a developer
I want to invoke Jelmore from the command line
So that I can test and debug without setting up the full event system

**Acceptance Criteria:**
- [ ] Click/Typer CLI application
- [ ] `jelmore start <provider>` command with --prompt, --session-id, --continue flags
- [ ] `jelmore sessions list [provider]` with --limit, --format options
- [ ] `jelmore sessions resume <session-id>` command
- [ ] `jelmore config show/set/validate` commands
- [ ] `jelmore listen` command for daemon mode
- [ ] Human-friendly output formatting (tables, colors)
- [ ] CLI translates to same command path as events

**Technical Notes:**
- Use Typer for modern CLI experience
- Rich for table formatting and colors
- CLI creates same command objects as event listener
- Config validation uses Pydantic

**Dependencies:** STORY-001, STORY-002, STORY-003, STORY-004

---

### STORY-007: Executor & Retry Logic

**Priority:** should-have
**Points:** 5 (effort:M)
**Type:** feature

**User Story:**
As a system operator
I want failed commands to retry automatically with backoff
So that transient failures don't require manual intervention

**Acceptance Criteria:**
- [ ] Command executor with retry loop (3x max)
- [ ] Exponential backoff: 1s, 2s, 4s between retries
- [ ] Side effect queue during execution
- [ ] Failure routing to DLQ after max retries
- [ ] Execution metrics: duration, retry count, success/failure
- [ ] Unit tests for retry behavior

**Technical Notes:**
- Use tenacity library for retry logic
- Side effects queued but not processed until command succeeds
- DLQ: agent.prompt.dlq with full context for debugging
- Metrics emitted as structured logs

**Dependencies:** STORY-002, STORY-005

---

### STORY-008: Hook System

**Priority:** should-have
**Points:** 5 (effort:M)
**Type:** feature

**User Story:**
As a developer
I want to add pre/post execution hooks to commands
So that I can implement cross-cutting concerns like auth and logging

**Acceptance Criteria:**
- [ ] Hook interface with execute(context) method
- [ ] Pre-execution hooks (run before command.invoke())
- [ ] Post-execution hooks (run after command.invoke())
- [ ] AuthHook implementation (validates credentials)
- [ ] LoggingHook implementation (structured logging)
- [ ] Hooks attachable via payload or builder
- [ ] Hook ordering guarantees (priority-based)
- [ ] Unit tests for hook execution order

**Technical Notes:**
- Hooks receive CommandContext with full state
- Pre-hooks can abort execution by raising exception
- Post-hooks receive CommandResult
- Builder can impose mandatory hooks (always auth, always log)

**Dependencies:** STORY-002

---

### STORY-009: Cross-Provider Session Search

**Priority:** could-have
**Points:** 5 (effort:M)
**Type:** feature

**User Story:**
As a user
I want to search across all my sessions regardless of provider
So that I can find past conversations by content

**Acceptance Criteria:**
- [ ] Full-text search indexing in Redis (inverted index)
- [ ] Search across all providers simultaneously
- [ ] Query by prompt/response content
- [ ] Filter by provider, date range, correlation ID
- [ ] CLI: `jelmore sessions search <query>` with filters
- [ ] Search results show relevant snippets
- [ ] Unit tests for search indexing and retrieval

**Technical Notes:**
- Index tokens from prompts and responses
- Redis sorted sets for efficient range queries
- Consider RediSearch module if available
- Fallback to simple SCAN if RediSearch unavailable

**Dependencies:** STORY-004, STORY-006

---

### STORY-010: Additional Providers & Observability

**Priority:** could-have
**Points:** 8 (effort:XL)
**Type:** feature

**User Story:**
As a user
I want to use Gemini CLI and Codex through Jelmore
So that I have a unified interface for all my agentic coders

**Acceptance Criteria:**
- [ ] Gemini provider adapter
- [ ] Codex provider adapter
- [ ] Event emission at tool calls, thinking, responses
- [ ] Structured logging with correlation IDs (structlog)
- [ ] All providers pass same integration test suite
- [ ] README with installation, configuration, usage
- [ ] Architecture diagram (Mermaid)
- [ ] Provider integration guide for adding new providers

**Technical Notes:**
- Each provider follows same interface
- Provider-specific config in ~/.config/jelmore/providers/{name}.yaml
- Events: agent.tool_call, agent.thinking, agent.response
- Use same subprocess pattern as Claude provider

**Dependencies:** STORY-003, STORY-005

---

## Sprint Allocation

### Sprint 1 (Weeks 1-2) - 31/30 points (103% utilization)

**Goal:** Deliver working Claude Code integration with CLI interface

**Stories:**
| Story | Title | Points | Priority |
|-------|-------|--------|----------|
| STORY-001 | Foundation & Project Structure | 5 | must-have |
| STORY-002 | Command System Core | 5 | must-have |
| STORY-003 | Claude Provider Integration | 8 | must-have |
| STORY-004 | Session Management | 5 | must-have |
| STORY-005 | Event-Driven System | 8 | must-have |

**Total:** 31 points

**Sprint 1 Deliverable:**
- Working `jelmore start claude --prompt "..."` command
- Sessions persist to Redis
- Bloodbank events consumed and emitted
- Docker environment with all services

**Risks:**
- Claude Code subprocess integration may have edge cases
- RabbitMQ connection handling in async context

---

### Sprint 2 (Weeks 3-4) - 28/30 points (93% utilization)

**Goal:** Complete CLI, resilience features, and multi-provider support

**Stories:**
| Story | Title | Points | Priority |
|-------|-------|--------|----------|
| STORY-006 | CLI Interface | 5 | should-have |
| STORY-007 | Executor & Retry Logic | 5 | should-have |
| STORY-008 | Hook System | 5 | should-have |
| STORY-009 | Cross-Provider Session Search | 5 | could-have |
| STORY-010 | Additional Providers & Observability | 8 | could-have |

**Total:** 28 points

**Sprint 2 Deliverable:**
- Full CLI with all commands
- Retry logic with exponential backoff
- Hook system for extensibility
- Search across sessions
- Gemini + Codex providers
- Complete documentation

**Risks:**
- Gemini/Codex CLI interfaces may differ significantly
- Search indexing performance with large session counts

---

## Requirements Coverage

| FR | Requirement | Story | Sprint |
|----|-------------|-------|--------|
| FR-1 | Provider Abstraction Layer | STORY-002, STORY-003 | 1 |
| FR-2 | Event-Driven Command System | STORY-005 | 1 |
| FR-3 | CLI Interface | STORY-006 | 2 |
| FR-4 | Command Chaining | STORY-002 | 1 |
| FR-5 | Hook System | STORY-008 | 2 |
| FR-6 | Session Management | STORY-004 | 1 |
| FR-7 | Cross-Provider Session Search | STORY-009 | 2 |
| FR-8 | Side Effect Processing | STORY-005, STORY-007 | 1, 2 |
| FR-9 | Observability | STORY-010 | 2 |
| FR-10 | Configuration Management | STORY-001 | 1 |

---

## Risks and Mitigation

**High:**
- Provider CLI API changes - Mitigation: Abstract interface, version pinning, integration tests
- Event message format evolution - Mitigation: Pydantic schema versioning, backward-compatible parsing

**Medium:**
- Session state corruption - Mitigation: Local backup, Redis AOF persistence, validation on load
- Command chain complexity - Mitigation: Correlation ID tracing, structured logging

**Low:**
- Retry logic resource exhaustion - Mitigation: Hard 3-retry limit, exponential backoff, DLQ routing

---

## Definition of Done

For a story to be considered complete:
- [ ] Code implemented and committed
- [ ] Unit tests written and passing (≥80% coverage)
- [ ] Integration tests passing (where applicable)
- [ ] Code reviewed (self-review for solo dev)
- [ ] Documentation updated (docstrings, README if needed)
- [ ] Plane ticket updated to "Done" status

---

## Next Steps

**Immediate:** Begin Sprint 1

Run `/bmad:dev-story STORY-001` to implement the first story.

**Sprint cadence:**
- Sprint length: 2 weeks
- Sprint planning: Day 1
- Sprint review: Day 10
- Sprint retrospective: Day 10
- **Sprint close:** Run `/bmad:sprint-close` to archive and create wiki log

---

**This plan was created using BMAD Method v6 - Phase 4 (Implementation Planning)**
