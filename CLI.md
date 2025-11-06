# Jelmore CLI Usage Guide

## Overview

Jelmore CLI provides convention-based LLM execution abstraction with detached Zellij sessions for n8n workflow integration and manual use.

**Key Features**:
- Convention over configuration (infer client, MCP servers, etc.)
- Detached Zellij sessions (non-blocking execution)
- Immediate return with session handle
- iMi worktree integration
- Config file support for reusable workflows

## Installation

```bash
cd /home/delorenj/code/jelmore
uv sync
uv run jelmore --help
```

## Quick Start

### Simple Inline Prompt

```bash
jelmore execute -p "Fix the login bug" --client claude
```

### Task from File

```bash
jelmore execute -f task.md --auto
```

### With iMi Worktree Context

```bash
jelmore execute -f task.md --worktree pr-458
```

### Config-Based Execution

```bash
jelmore execute --config examples/configs/pr-review.json
```

## Usage Patterns

### Pattern 1: Explicit (All Options Specified)

```bash
jelmore execute \
  --client claude \
  --file /some/task.md \
  --path /some/repo/root \
  --detached \
  --session-name "my-session"
```

**Use when**: You need full control over execution parameters.

### Pattern 2: Convention-Based (Auto Mode)

```bash
jelmore execute -p "Create a react dashboard" --auto
```

**Auto-inferred**:
- Client: `claude` (detected "react" in prompt)
- Working directory: Current directory
- Session name: Auto-generated with timestamp
- MCP servers: Auto-enabled based on prompt content
- Model tier: `balanced` (default)

**Use when**: You want jelmore to make smart decisions.

### Pattern 3: Config-Based (Reusable Workflows)

```bash
jelmore execute --config pr-review.json
```

**Benefits**:
- Reusable workflow definitions
- Variable substitution
- Team-shareable configurations

**Use when**: You have repeatable workflow patterns.

## CLI Commands

### execute

Execute a task with an LLM client.

```bash
jelmore execute [OPTIONS]
```

#### Task Specification (mutually exclusive)

- `--prompt, -p TEXT` - Inline prompt text
- `--file, -f PATH` - Task file path
- `--template, -t NAME` - Template name from `~/.config/jelmore/templates/`

#### Client Selection

- `--client, -c NAME` - LLM client: `claude`, `claude-flow`, `gptme`, `copilot`, `amazonq`

#### Execution Context

- `--path PATH` - Working directory (default: current or iMi resolved)
- `--worktree ID` - Use iMi to resolve worktree by ID
- `--context PATH` - Additional context files (repeatable)

#### Execution Mode

- `--detached, -d` - Detached Zellij session (default: true)
- `--interactive, -i` - Foreground interactive mode
- `--session-name NAME` - Explicit session name

#### Model Configuration

- `--model-tier TIER` - Model tier: `fast`, `balanced`, `powerful`, `reasoning`
- `--model NAME` - Explicit model name override

#### MCP Servers

- `--mcp SERVER` - Enable specific MCP servers (repeatable)
- `--no-mcp` - Disable all MCP servers

#### Configuration

- `--config PATH` - Load config file
- `--profile NAME` - Load profile from `~/.config/jelmore/profiles/`

#### Automation

- `--auto` - Full auto mode (infer everything)

#### Output

- `--json` - JSON output for scripting
- `--quiet` - Suppress output except essentials

### config

Manage configuration profiles.

```bash
jelmore config list                   # List available profiles
jelmore config show <name>            # Show profile contents
jelmore config edit <name>            # Edit profile in $EDITOR
jelmore config create <name>          # Create new profile
jelmore config validate <path>        # Validate config file
```

### session

Manage execution sessions.

```bash
jelmore session list                  # List all Zellij sessions
jelmore session attach <id>           # Attach to session
jelmore session logs <id>             # Stream session logs
jelmore session kill <id>             # Terminate session
jelmore session status <id>           # Get session status
```

### status

Get execution status.

```bash
jelmore status <execution-id>         # Get status once
jelmore status <execution-id> --watch # Watch status (refresh every 2s)
jelmore status <execution-id> --json  # JSON output
```

## Convention Engine

The convention engine applies smart defaults based on prompt content.

### Client Inference

Prompt patterns automatically select the best client:

| Pattern | Inferred Client |
|---------|----------------|
| `react`, `typescript` | `claude` (Claude Code) |
| `python`, `api` | `gptme` |
| `review`, `refactor`, `research` | `claude-flow` (swarm) |
| Default | `gptme` |

### MCP Server Inference

Prompt patterns automatically enable MCP servers:

| Pattern | Enabled MCP Servers |
|---------|-------------------|
| `github`, `pr`, `pull request` | `github-mcp` |
| `docs`, `documentation` | `obsidian-mcp` |
| `trello`, `card` | `triumph-trello` |
| Always | `bloodbank-mcp` |

### Model Tier Mapping

| Tier | gptme | Claude Code | Claude Flow |
|------|-------|------------|-------------|
| `fast` | `$FLASHL` (Gemini 2.5 Flash Lite) | `claude-3-5-haiku` | N/A |
| `balanced` | `$KK` (Kimi K2) | `claude-3-5-sonnet` | Default |
| `powerful` | `$GPRO` (Gemini 2.5 Pro) | `claude-3-opus` | N/A |
| `reasoning` | `$DSR` (DeepSeek R1) | N/A | N/A |

## Configuration Files

Config files use JSON with variable substitution.

### Schema

```json
{
  "name": "Workflow Name",
  "description": "What this workflow does",
  "client": "claude|claude-flow|gptme",
  "mode": "detached|interactive|background",
  "task": {
    "template": "/path/to/template.md",
    "context": {
      "var1": "{{ VAR1 }}",
      "var2": "{{ VAR2 }}"
    }
  },
  "execution": {
    "strategy": "swarm",
    "max_agents": 4,
    "model_tier": "balanced"
  },
  "environment": {
    "worktree_resolver": "imi",
    "mcp_servers": ["github-mcp", "bloodbank-mcp"]
  },
  "observability": {
    "session_prefix": "workflow-name",
    "log_path": "/tmp/jelmore/{{ TIMESTAMP }}.log"
  }
}
```

### Variable Substitution

Variables in `{{ VAR_NAME }}` format are replaced at execution time.

**Built-in variables**:
- `{{ TIMESTAMP }}` - Current timestamp (YYYYMMDD-HHMMSS)
- `{{ DATE }}` - Current date (YYYY-MM-DD)
- `{{ TIME }}` - Current time (HH:MM:SS)

**Custom variables** via CLI:
```bash
jelmore execute --config pr-review.json --var PR_NUMBER=458 --var REPO=n8n
```

## n8n Integration

### Execute Command Node

```javascript
{
  "command": "uv run jelmore execute -f /path/to/task.md --worktree pr-{{ $json.pr_number }} --auto --json",
  "timeout": 5000
}
```

Returns immediately with session handle:

```json
{
  "execution_id": "abc123",
  "session_name": "jelmore-pr-458-20251103-143022",
  "client": "claude-flow",
  "log_path": "/tmp/jelmore-abc123.log",
  "working_directory": "/home/delorenj/code/n8n/pr-458",
  "started_at": "2025-11-03T14:30:22"
}
```

### Parse Response Node

```javascript
const output = JSON.parse($('Execute Command').json.stdout);

return {
  sessionName: output.session_name,
  attachCommand: `zellij attach ${output.session_name}`,
  executionId: output.execution_id,
  logPath: output.log_path
};
```

### Monitor Session (Optional)

```javascript
{
  "command": "uv run jelmore status {{ $json.executionId }} --json",
  "continueOnFail": true
}
```

## Examples

### Example 1: PR Review with Auto Inference

```bash
jelmore execute \
  -f ~/code/DeLoDocs/AI/Agents/Generic/My\ Personal\ PR\ Review\ Representative.md \
  --worktree pr-458 \
  --auto
```

**What happens**:
1. Detects "review" in prompt → selects `claude-flow` client
2. Resolves worktree via iMi: `/home/delorenj/code/n8n/pr-458`
3. Auto-enables `github-mcp` and `bloodbank-mcp`
4. Spawns detached Zellij session
5. Returns immediately with session name

### Example 2: Feature Development

```bash
jelmore execute \
  -p "Implement user authentication with JWT" \
  --client claude \
  --path /home/delorenj/code/myapp \
  --model-tier balanced \
  --mcp obsidian-mcp
```

**What happens**:
1. Uses Claude Code client explicitly
2. Executes in specified directory
3. Uses balanced model tier (Sonnet)
4. Enables obsidian-mcp for docs access
5. Returns session handle immediately

### Example 3: Bug Fix with Reasoning Model

```bash
jelmore execute \
  -f bug-report.md \
  --client gptme \
  --model-tier reasoning \
  --worktree fix-login-bug
```

**What happens**:
1. Uses gptme with DeepSeek R1 (reasoning tier)
2. Resolves worktree via iMi
3. Spawns detached session
4. Returns immediately

## Observability

### Attach to Running Session

```bash
# From jelmore output
zellij attach jelmore-pr-458-20251103-143022

# Or via session list
jelmore session list
jelmore session attach <session-name>
```

### Stream Logs

```bash
# From log path in output
tail -f /tmp/jelmore-abc123.log

# Or via session command
jelmore session logs <session-id>
```

### Query Status

```bash
jelmore status abc123

# Watch continuously
jelmore status abc123 --watch

# JSON output
jelmore status abc123 --json
```

## Advanced Usage

### Multiple Context Files

```bash
jelmore execute \
  -f task.md \
  --context docs/api.md \
  --context docs/architecture.md \
  --context examples/usage.py
```

### Custom Session Name

```bash
jelmore execute \
  -p "Refactor auth module" \
  --session-name auth-refactor-$(date +%Y%m%d)
```

### Disable MCP Servers

```bash
jelmore execute -p "Simple task" --no-mcp
```

### Background Mode (No Session)

```bash
jelmore execute -p "Run tests" --no-detached --background
```

## Troubleshooting

### Session Not Found

```bash
# List all sessions
jelmore session list

# Check for exited sessions
zellij list-sessions
```

### iMi Resolution Failed

```bash
# Test iMi manually
iMi go pr-458

# Check iMi configuration
iMi list
```

### Client Not Available

```bash
# Check if client is installed
which claude
which gptme
```

### MCP Server Issues

```bash
# Disable MCP and try again
jelmore execute -p "test" --no-mcp

# Check MCP server availability
npx claude mcp list
```

## Next Steps

1. **Create custom profiles**: Add workflow configs to `~/.config/jelmore/profiles/`
2. **Create templates**: Add task templates to `~/.config/jelmore/templates/`
3. **Integrate with n8n**: Use Execute Command nodes with `--json` output
4. **Monitor sessions**: Set up Bloodbank event subscribers for completion tracking

## See Also

- [Jelmore API Documentation](./README.md)
- [Shell Context Independence Pattern](../.claude/skills/shell-automation-patterns.md)
- [n8n Workflow Integration](./examples/n8n-workflows/)
