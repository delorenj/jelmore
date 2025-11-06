"""
Execute command handler with convention engine
"""
import subprocess
import json
from pathlib import Path
from typing import Optional
from datetime import datetime
from .main import ClientType, ModelTier, ExecutionMode
import typer
import tempfile


class ConventionEngine:
    """Apply smart defaults based on task context"""

    # Tech stack patterns for client inference
    TECH_PATTERNS = {
        r'\breact\b': ClientType.CLAUDE,
        r'\btypescript\b': ClientType.CLAUDE,
        r'\bpython\b': ClientType.GPTME,
        r'\bapi\b': ClientType.GPTME,
        r'\breview\b': ClientType.CLAUDE_FLOW,
        r'\brefactor\b': ClientType.CLAUDE_FLOW,
        r'\bresearch\b': ClientType.CLAUDE_FLOW,
    }

    # MCP server patterns
    MCP_PATTERNS = {
        r'\bgithub\b|\bpr\b|\bpull request\b': ['github-mcp'],
        r'\bdocs\b|\bdocumentation\b': ['obsidian-mcp'],
        r'\btrello\b|\bcard\b': ['triumph-trello'],
    }

    def infer_client(self, prompt: str, auto_mode: bool) -> Optional[ClientType]:
        """Infer client from prompt content"""
        if not auto_mode:
            return None

        import re
        prompt_lower = prompt.lower()

        for pattern, client in self.TECH_PATTERNS.items():
            if re.search(pattern, prompt_lower):
                return client

        # Default to gptme
        return ClientType.GPTME

    def infer_mcp_servers(self, prompt: str, enable_mcp: bool) -> list[str]:
        """Infer MCP servers from prompt content"""
        if not enable_mcp:
            return []

        import re
        servers = []
        prompt_lower = prompt.lower()

        for pattern, mcp_list in self.MCP_PATTERNS.items():
            if re.search(pattern, prompt_lower):
                servers.extend(mcp_list)

        # Always add bloodbank for event publishing
        if 'bloodbank-mcp' not in servers:
            servers.append('bloodbank-mcp')

        return list(set(servers))  # Dedupe


def execute_task(
    prompt: Optional[str],
    file: Optional[Path],
    template: Optional[str],
    client: Optional[ClientType],
    path: Optional[Path],
    worktree: Optional[str],
    context: list[Path],
    mode: ExecutionMode,
    session_name: Optional[str],
    model_tier: ModelTier,
    model_override: Optional[str],
    mcp_servers: list[str],
    enable_mcp: bool,
    config_file: Optional[Path],
    profile: Optional[str],
    auto_mode: bool,
    publish_events: bool,
    json_output: bool,
    quiet: bool,
):
    """
    Main execution handler with convention engine.

    Strategy:
    1. Load/merge configuration (config file > profile > CLI args)
    2. Get prompt content from various sources
    3. Apply conventions (infer client, MCP servers, etc.)
    4. Resolve working directory (iMi if needed)
    5. Spawn detached Zellij session
    6. Return handle immediately
    """
    convention_engine = ConventionEngine()

    # Step 1: Get prompt content
    prompt_content = _get_prompt_content(prompt, file, template)
    if not prompt_content:
        typer.echo("Error: No prompt provided", err=True)
        raise typer.Exit(1)

    # Step 2: Apply conventions
    if not client:
        client = convention_engine.infer_client(prompt_content, auto_mode)
        if not client:
            client = ClientType.CLAUDE  # Final fallback

    if enable_mcp and not mcp_servers:
        mcp_servers = convention_engine.infer_mcp_servers(prompt_content, enable_mcp)

    # Step 3: Resolve working directory
    working_dir = _resolve_working_directory(path, worktree)

    # Step 4: Generate session name
    if not session_name:
        task_id = _extract_task_id(worktree, working_dir)
        session_name = f"jelmore-{task_id}-{datetime.now():%Y%m%d-%H%M%S}"

    # Step 5: Execute based on mode
    if mode == ExecutionMode.DETACHED:
        handle = _execute_detached(
            prompt=prompt_content,
            client=client,
            working_dir=working_dir,
            session_name=session_name,
            model_tier=model_tier,
            mcp_servers=mcp_servers,
            publish_events=publish_events,
        )

        # Output
        if json_output:
            typer.echo(json.dumps(handle, indent=2))
        elif not quiet:
            typer.echo("🚀 Task launched in background")
            typer.echo("━" * 40)
            typer.echo(f"Session: {handle['session_name']}")
            typer.echo(f"Execution ID: {handle['execution_id']}")
            typer.echo("")
            typer.echo(f"Attach: zellij attach {handle['session_name']}")
            typer.echo(f"Logs: tail -f {handle['log_path']}")

    elif mode == ExecutionMode.INTERACTIVE:
        _execute_interactive(
            prompt=prompt_content,
            client=client,
            working_dir=working_dir,
            model_tier=model_tier,
        )

    else:  # BACKGROUND
        _execute_background(
            prompt=prompt_content,
            client=client,
            working_dir=working_dir,
        )


def _get_prompt_content(
    prompt: Optional[str],
    file: Optional[Path],
    template: Optional[str]
) -> str:
    """Get prompt content from various sources"""
    if prompt:
        return prompt
    elif file:
        if not file.exists():
            typer.echo(f"Error: File not found: {file}", err=True)
            raise typer.Exit(1)
        return file.read_text()
    elif template:
        template_path = Path.home() / ".config/jelmore/templates" / f"{template}.md"
        if not template_path.exists():
            typer.echo(f"Error: Template not found: {template}", err=True)
            raise typer.Exit(1)
        return template_path.read_text()
    return ""


def _resolve_working_directory(
    path: Optional[Path],
    worktree: Optional[str]
) -> Path:
    """Resolve working directory, using iMi if needed"""
    if path:
        return path.resolve()
    elif worktree:
        # Use iMi to resolve worktree
        result = subprocess.run(
            ["iMi", "go", worktree],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            typer.echo(f"Error: iMi failed to resolve worktree: {worktree}", err=True)
            raise typer.Exit(1)
        return Path(result.stdout.strip())
    else:
        return Path.cwd()


def _extract_task_id(worktree: Optional[str], working_dir: Path) -> str:
    """Extract task identifier for session naming"""
    if worktree:
        return worktree
    return working_dir.name


def _execute_detached(
    prompt: str,
    client: ClientType,
    working_dir: Path,
    session_name: str,
    model_tier: ModelTier,
    mcp_servers: list[str],
    publish_events: bool,
) -> dict:
    """
    Execute in detached Zellij session.

    Returns immediately with session handle.
    """
    import uuid

    execution_id = str(uuid.uuid4())[:8]

    # Create temp script for Zellij execution
    temp_script = tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.sh',
        delete=False,
        prefix='jelmore-'
    )

    # Build execution script based on client
    script_content = _build_execution_script(
        client=client,
        prompt=prompt,
        working_dir=working_dir,
        model_tier=model_tier,
        mcp_servers=mcp_servers,
        execution_id=execution_id,
    )

    temp_script.write(script_content)
    temp_script.close()

    # Make executable
    import os
    os.chmod(temp_script.name, 0o755)

    # Log path
    log_path = f"/tmp/jelmore-{execution_id}.log"

    # Launch detached Zellij session with logging
    # First create the session in background
    subprocess.run(
        ["zellij", "attach", session_name, "--create-background"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

    # Then run the script in that session with output redirected to log
    # We need to wrap the script execution with logging redirection
    wrapper_script = tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.sh',
        delete=False,
        prefix='jelmore-wrapper-'
    )
    wrapper_script.write(f"""#!/bin/zsh
set -euo pipefail
exec > >(tee "{log_path}") 2>&1
{temp_script.name}
""")
    wrapper_script.close()
    os.chmod(wrapper_script.name, 0o755)

    # Run the wrapper script in the detached session
    subprocess.Popen(
        [
            "zellij",
            "run",
            "--name", f"jelmore-{execution_id}",
            "--cwd", str(working_dir),
            "--",
            wrapper_script.name
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Clean up scripts after delay
    def cleanup():
        import time
        time.sleep(5)  # Increased delay to ensure zellij has started
        try:
            os.unlink(temp_script.name)
            os.unlink(wrapper_script.name)
        except FileNotFoundError:
            pass

    import threading
    threading.Thread(target=cleanup, daemon=True).start()

    return {
        "execution_id": execution_id,
        "session_name": session_name,
        "client": client.value,
        "log_path": log_path,
        "working_directory": str(working_dir),
        "started_at": datetime.now().isoformat(),
    }


def _build_execution_script(
    client: ClientType,
    prompt: str,
    working_dir: Path,
    model_tier: ModelTier,
    mcp_servers: list[str],
    execution_id: str,
) -> str:
    """Build bash script for execution"""

    # Model tier mapping
    model_map = {
        ClientType.GPTME: {
            ModelTier.FAST: "$FLASHL",
            ModelTier.BALANCED: "$KK",
            ModelTier.POWERFUL: "$GPRO",
            ModelTier.REASONING: "$DSR",
        },
        ClientType.CLAUDE: {
            ModelTier.FAST: "claude-3-5-haiku-20241022",
            ModelTier.BALANCED: "claude-3-5-sonnet-20241022",
            ModelTier.POWERFUL: "claude-3-opus-20240229",
        },
        ClientType.CLAUDE_FLOW: {
            ModelTier.BALANCED: "default",
        }
    }

    # Escape prompt for bash
    prompt_escaped = prompt.replace('"', '\\"').replace('$', '\\$')

    # Preserve critical environment variables
    import os
    import shlex
    claude_oauth = os.environ.get('CLAUDE_CODE_OAUTH_TOKEN', '')

    # Use shlex.quote to safely escape the token for bash
    # This handles special characters like $, ", `, etc.
    claude_oauth_escaped = shlex.quote(claude_oauth) if claude_oauth else ''

    script = f"""#!/bin/zsh
set -euo pipefail

export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"

# Preserve Claude Code OAuth token for Max Pro plan
export CLAUDE_CODE_OAUTH_TOKEN={claude_oauth_escaped}

# Unset ANTHROPIC_API_KEY to allow OAuth to take precedence
# (API key auth has higher priority than OAuth)
unset ANTHROPIC_API_KEY

echo "🔍 Jelmore Execution"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Execution ID: {execution_id}"
echo "Client: {client.value}"
echo "Session: $ZELLIJ_SESSION_NAME"
echo "Directory: {working_dir}"
echo ""

cd "{working_dir}"

"""

    # Client-specific execution
    if client == ClientType.CLAUDE:
        script += f"""
echo "🚀 Launching Claude Code..."
claude "{prompt_escaped}"
"""

    elif client == ClientType.CLAUDE_FLOW:
        script += f"""
echo "🚀 Launching Claude Flow Swarm..."
npx claude-flow@alpha swarm "{prompt_escaped}" \\
    --strategy development \\
    --parallel \\
    --max-agents 4 \\
    --claude
"""

    elif client == ClientType.GPTME:
        model = model_map[ClientType.GPTME].get(model_tier, "$KK")
        script += f"""
echo "🚀 Launching gptme..."
gptme -m {model} "{prompt_escaped}"
"""

    script += f"""
EXIT_CODE=$?

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ $EXIT_CODE -eq 0 ]]; then
    echo "✅ Execution completed"
else
    echo "❌ Execution failed: $EXIT_CODE"
fi
echo "Session: $ZELLIJ_SESSION_NAME"
echo "Press any key to close, or Ctrl+C to keep open..."
read -k1

exit $EXIT_CODE
"""

    return script


def _execute_interactive(
    prompt: str,
    client: ClientType,
    working_dir: Path,
    model_tier: ModelTier,
):
    """Execute in foreground interactive mode"""
    typer.echo(f"Interactive mode not yet implemented for {client}")
    raise typer.Exit(1)


def _execute_background(
    prompt: str,
    client: ClientType,
    working_dir: Path,
):
    """Execute as background daemon"""
    typer.echo(f"Background mode not yet implemented for {client}")
    raise typer.Exit(1)
