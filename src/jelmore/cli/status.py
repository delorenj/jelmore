"""Status querying"""
import typer
import time


def handle_status(execution_id: str, watch: bool, json_output: bool):
    """Handle status subcommand"""
    if watch:
        try:
            while True:
                _print_status(execution_id, json_output)
                time.sleep(2)
        except KeyboardInterrupt:
            typer.echo("\nStopped watching")
    else:
        _print_status(execution_id, json_output)


def _print_status(execution_id: str, json_output: bool):
    """Print current status"""
    # TODO: Query actual status from jelmore API or session
    if json_output:
        typer.echo(f'{{"execution_id": "{execution_id}", "status": "running"}}')
    else:
        typer.echo(f"Execution ID: {execution_id}")
        typer.echo(f"Status: running")
