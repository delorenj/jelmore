"""Session management"""
import typer
import subprocess


def handle_session(action: str, session_id: str | None):
    """Handle session subcommand"""
    if action == "list":
        # List Zellij sessions
        result = subprocess.run(
            ["zellij", "list-sessions"],
            capture_output=True,
            text=True
        )
        typer.echo(result.stdout)

    elif action == "attach" and session_id:
        # Attach to session
        subprocess.run(["zellij", "attach", session_id])

    elif action == "logs" and session_id:
        typer.echo(f"Streaming logs for: {session_id}")
        # TODO: Stream session logs

    elif action == "kill" and session_id:
        subprocess.run(["zellij", "kill-session", session_id])
        typer.echo(f"✅ Killed session: {session_id}")

    elif action == "status" and session_id:
        typer.echo(f"Status for: {session_id}")
        # TODO: Query session status

    else:
        typer.echo(f"Unknown action or missing session ID", err=True)
        raise typer.Exit(1)
