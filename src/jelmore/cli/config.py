"""Config management"""
import typer


def handle_config(action: str, name: str | None):
    """Handle config subcommand"""
    if action == "list":
        typer.echo("Available profiles:")
        # TODO: List profiles from ~/.config/jelmore/profiles/
    elif action == "show" and name:
        typer.echo(f"Showing profile: {name}")
        # TODO: Show profile contents
    elif action == "edit" and name:
        typer.echo(f"Editing profile: {name}")
        # TODO: Open in $EDITOR
    elif action == "create" and name:
        typer.echo(f"Creating profile: {name}")
        # TODO: Interactive creation
    elif action == "validate" and name:
        typer.echo(f"Validating config: {name}")
        # TODO: Validate config file
    else:
        typer.echo(f"Unknown action: {action}", err=True)
        raise typer.Exit(1)
