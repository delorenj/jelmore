"""Main CLI application for Jelmore."""

import typer
from rich.console import Console

app = typer.Typer(
    name="jelmore",
    help="Event-driven orchestration layer for agentic coders",
    no_args_is_help=True,
)
console = Console()


@app.command()
def version() -> None:
    """Show Jelmore version."""
    from jelmore import __version__

    console.print(f"jelmore v{__version__}")


@app.command()
def start(
    provider: str = typer.Argument(..., help="Provider to use (claude, gemini, codex)"),
    prompt: str | None = typer.Option(None, "--prompt", "-p", help="Initial prompt"),
    session_id: str | None = typer.Option(None, "--session-id", "-s", help="Resume session"),
    continue_session: bool = typer.Option(False, "--continue", "-c", help="Continue last session"),
) -> None:
    """Start a new provider session."""
    console.print(f"[bold green]Starting {provider} session...[/bold green]")
    # Placeholder - will be implemented in STORY-003
    console.print("[yellow]Not yet implemented[/yellow]")


@app.command()
def listen(
    queue: str = typer.Option("agent.prompt", "--queue", "-q", help="Bloodbank queue"),
    workers: int = typer.Option(5, "--workers", "-w", help="Number of workers"),
) -> None:
    """Listen for Bloodbank events (daemon mode)."""
    console.print(f"[bold green]Listening on queue: {queue} with {workers} workers[/bold green]")
    # Placeholder - will be implemented in STORY-005
    console.print("[yellow]Not yet implemented[/yellow]")


if __name__ == "__main__":
    app()
