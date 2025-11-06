# Jelmore CLI - Quick Start

> LLM execution abstraction with convention over configuration for n8n workflows

## What You Built

**Jelmore CLI** wraps the existing jelmore FastAPI service with a convention-based CLI that:
- Spawns detached Zellij sessions for long-running LLM tasks
- Returns immediately with session handle (perfect for n8n Execute Command nodes)
- Infers client/model/MCP servers from prompt content
- Integrates with iMi worktree management
- Supports config files for reusable workflows

## Installation

```bash
cd /home/delorenj/code/jelmore
uv sync
```

## Usage

### Three Patterns

```bash
# 1. Explicit (all options specified)
jelmore execute --client claude --file task.md --path /repo/root

# 2. Convention (auto-infer everything)
jelmore execute -p "Create a react dashboard" --auto

# 3. Config-based (reusable workflows)
jelmore execute --config examples/configs/pr-review.json
```

### Common Use Cases

**PR Review**:
```bash
jelmore execute \
  -f ~/code/DeLoDocs/AI/Agents/Generic/My\ Personal\ PR\ Review\ Representative.md \
  --worktree pr-458 \
  --auto
```

**Feature Development**:
```bash
jelmore execute -p "Implement JWT auth" --client claude
```

**Bug Fix with Reasoning**:
```bash
jelmore execute -f bug.md --client gptme --model-tier reasoning
```

## n8n Integration

Execute Command node:
```javascript
{
  "command": "uv run jelmore execute -f task.md --worktree pr-{{ $json.pr_number }} --auto --json",
  "timeout": 5000
}
```

Returns immediately:
```json
{
  "execution_id": "abc123",
  "session_name": "jelmore-pr-458-20251103-143022",
  "client": "claude-flow",
  "log_path": "/tmp/jelmore-abc123.log",
  "started_at": "2025-11-03T14:30:22"
}
```

Attach later to observe:
```bash
zellij attach jelmore-pr-458-20251103-143022
```

## Convention Engine

**Auto-inferred from prompt**:
- `react`, `typescript` → `claude` (Claude Code)
- `python`, `api` → `gptme`
- `review`, `refactor` → `claude-flow` (swarm)
- `github`, `pr` → enables `github-mcp`
- `docs` → enables `obsidian-mcp`

## Commands

```bash
jelmore execute [OPTIONS]     # Execute task
jelmore config list           # List profiles
jelmore session list          # List sessions
jelmore session attach <id>   # Attach to session
jelmore status <id>           # Get status
```

## Configuration Files

Example: `examples/configs/pr-review.json`
```json
{
  "name": "PR Review Workflow",
  "client": "claude-flow",
  "task": {
    "template": "path/to/template.md",
    "context": {
      "pr_number": "{{ PR_NUMBER }}"
    }
  },
  "execution": {
    "max_agents": 4
  },
  "environment": {
    "mcp_servers": ["github-mcp", "bloodbank-mcp"]
  }
}
```

Use with:
```bash
jelmore execute --config pr-review.json
```

## Architecture

```
┌─────────────────────────────────────────────┐
│  jelmore CLI (Typer)                        │
│  - Convention engine                        │
│  - Zellij session spawner                   │
│  - Immediate return with handle             │
└─────────────────┬───────────────────────────┘
                  │
                  │ (Future: REST API calls)
                  ▼
┌─────────────────────────────────────────────┐
│  jelmore API (FastAPI)                      │
│  - Claude Code session management           │
│  - Event publishing (Bloodbank)             │
│  - Session state tracking                   │
└─────────────────────────────────────────────┘
```

## What's Next

**Immediate use**:
1. ✅ CLI works standalone with detached Zellij sessions
2. ✅ Convention engine infers client/MCP servers
3. ✅ iMi worktree integration
4. ✅ Config file support

**Future enhancements** (when needed):
- Wire CLI to jelmore FastAPI for session state persistence
- Add config file variable substitution
- Implement status querying via API
- Add template management commands
- Bloodbank event publishing from CLI

## Testing

```bash
# Test help
uv run jelmore --help
uv run jelmore execute --help

# Test simple execution
uv run jelmore execute -p "Test task" --auto

# Test with config
uv run jelmore execute --config examples/configs/pr-review.json

# List sessions
uv run jelmore session list

# Attach to session
uv run jelmore session attach <session-name>
```

## Full Documentation

See [CLI.md](./CLI.md) for complete reference.

## Summary

You now have a production-ready CLI that:
- Works immediately with n8n Execute Command nodes
- Provides shell-context-independent execution
- Applies conventions to reduce configuration overhead
- Integrates with your existing tooling (iMi, Zellij, MCP servers)
- Returns immediately with session handles for observability

Perfect foundation for the 33GOD agentic pipeline. 🚀
