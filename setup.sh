#!/usr/bin/env zsh

# mise configuration for Jelmore project
mise install python@3.12
mise use python@3.12

# Create virtual environment with uv
uv venv

# Activate and install dependencies
source .venv/bin/activate
uv pip install -e ".[dev]"

echo "✅ Jelmore environment setup complete!"
echo "Run 'source .venv/bin/activate' to activate the environment"
