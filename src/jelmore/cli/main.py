"""
Jelmore CLI - LLM execution abstraction layer

Provides convention-based CLI for executing long-running LLM tasks
with detached Zellij sessions and immediate return for n8n workflows.
"""
import typer
from typing import Optional
from pathlib import Path
from enum import Enum

app = typer.Typer(
    name="jelmore",
    help="LLM execution abstraction with convention over configuration",
    add_completion=False
)


class ClientType(str, Enum):
    """Supported LLM clients"""
    CLAUDE = "claude"
    CLAUDE_FLOW = "claude-flow"
    GPTME = "gptme"
    COPILOT = "copilot"
    AMAZONQ = "amazonq"


class ModelTier(str, Enum):
    """Model performance tiers"""
    FAST = "fast"
    BALANCED = "balanced"
    POWERFUL = "powerful"
    REASONING = "reasoning"


class ExecutionMode(str, Enum):
    """Execution modes"""
    DETACHED = "detached"
    INTERACTIVE = "interactive"
    BACKGROUND = "background"


@app.command(name="execute", help="Execute a task (default command)")
def execute(
    # Task specification (mutually exclusive)
    prompt: Optional[str] = typer.Option(
        None, "--prompt", "-p",
        help="Inline prompt text"
    ),
    file: Optional[Path] = typer.Option(
        None, "--file", "-f",
        help="Task file path"
    ),
    template: Optional[str] = typer.Option(
        None, "--template", "-t",
        help="Template name from ~/.config/jelmore/templates/"
    ),

    # Client selection
    client: Optional[ClientType] = typer.Option(
        None, "--client", "-c",
        help="LLM client to use"
    ),

    # Execution context
    path: Optional[Path] = typer.Option(
        None, "--path",
        help="Working directory (default: current or iMi resolved)"
    ),
    worktree: Optional[str] = typer.Option(
        None, "--worktree",
        help="Use iMi to resolve worktree by ID"
    ),
    context: Optional[list[Path]] = typer.Option(
        None, "--context",
        help="Additional context files"
    ),

    # Execution mode
    detached: bool = typer.Option(
        True, "--detached/--no-detached", "-d",
        help="Detached Zellij session (default: true)"
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i",
        help="Foreground interactive mode"
    ),

    # Session management
    session_name: Optional[str] = typer.Option(
        None, "--session-name",
        help="Explicit session name"
    ),

    # Model configuration
    model_tier: ModelTier = typer.Option(
        ModelTier.BALANCED, "--model-tier",
        help="Model tier (fast/balanced/powerful/reasoning)"
    ),
    model: Optional[str] = typer.Option(
        None, "--model",
        help="Explicit model name override"
    ),

    # MCP servers
    mcp: Optional[list[str]] = typer.Option(
        None, "--mcp",
        help="Enable specific MCP servers"
    ),
    no_mcp: bool = typer.Option(
        False, "--no-mcp",
        help="Disable all MCP servers"
    ),

    # Configuration
    config: Optional[Path] = typer.Option(
        None, "--config",
        help="Load config file"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile",
        help="Load profile from ~/.config/jelmore/profiles/"
    ),

    # Automation
    auto: bool = typer.Option(
        False, "--auto",
        help="Full auto mode (infer everything)"
    ),

    # Bloodbank integration
    publish: bool = typer.Option(
        True, "--publish/--no-publish",
        help="Publish execution events to Bloodbank"
    ),

    # Output
    json_output: bool = typer.Option(
        False, "--json",
        help="JSON output for scripting"
    ),
    quiet: bool = typer.Option(
        False, "--quiet",
        help="Suppress output except essentials"
    ),
):
    """
    Execute a task with an LLM client.

    Examples:

        # Simple inline prompt
        jelmore execute -p "Fix the login bug" --client claude

        # Task from file with auto context
        jelmore execute -f task.md --auto

        # Config-based execution
        jelmore execute --config pr-review.json

        # Profile-based shorthand
        jelmore execute --profile pr-review

        # iMi worktree context
        jelmore execute -f task.md --worktree pr-458
    """
    from .execute import execute_task

    # Determine execution mode
    if interactive:
        mode = ExecutionMode.INTERACTIVE
    elif detached:
        mode = ExecutionMode.DETACHED
    else:
        mode = ExecutionMode.BACKGROUND

    # Delegate to execute handler
    execute_task(
        prompt=prompt,
        file=file,
        template=template,
        client=client,
        path=path,
        worktree=worktree,
        context=context or [],
        mode=mode,
        session_name=session_name,
        model_tier=model_tier,
        model_override=model,
        mcp_servers=mcp or [],
        enable_mcp=not no_mcp,
        config_file=config,
        profile=profile,
        auto_mode=auto,
        publish_events=publish,
        json_output=json_output,
        quiet=quiet,
    )


@app.command(name="config")
def config_cmd(
    action: str = typer.Argument(..., help="Action: list, show, edit, create, validate"),
    name: Optional[str] = typer.Argument(None, help="Config name"),
):
    """Manage configuration profiles"""
    from .config import handle_config
    handle_config(action, name)


@app.command(name="session")
def session_cmd(
    action: str = typer.Argument(..., help="Action: list, status, attach, logs, kill"),
    session_id: Optional[str] = typer.Argument(None, help="Session ID"),
):
    """Manage execution sessions"""
    from .session import handle_session
    handle_session(action, session_id)


@app.command(name="status")
def status_cmd(
    execution_id: str = typer.Argument(..., help="Execution ID"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Watch status"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Get execution status"""
    from .status import handle_status
    handle_status(execution_id, watch, json_output)


# Default command shortcut
@app.callback(invoke_without_command=True)
def default(ctx: typer.Context):
    """
    Default behavior: if no subcommand given and there are arguments,
    assume 'execute' command.
    """
    if ctx.invoked_subcommand is None:
        # Check if there are any options that suggest execute
        if ctx.params:
            ctx.invoke(execute)
        else:
            typer.echo(ctx.get_help())


if __name__ == "__main__":
    app()
