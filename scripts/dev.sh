#!/usr/bin/env bash

# Jelmore Development Helper Script

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

function print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

function print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

function print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

function show_help() {
    echo "Jelmore Development Helper"
    echo ""
    echo "Usage: ./scripts/dev.sh [command]"
    echo ""
    echo "Commands:"
    echo "  setup       - Initial project setup"
    echo "  start       - Start all services"
    echo "  stop        - Stop all services"
    echo "  restart     - Restart all services"
    echo "  logs        - Show service logs"
    echo "  test        - Run tests"
    echo "  format      - Format code"
    echo "  api         - Start API server"
    echo "  shell       - Open Python shell with project context"
    echo "  clean       - Clean up containers and volumes"
    echo "  help        - Show this help message"
}


function setup() {
    print_info "Setting up Jelmore..."
    
    # Copy env file if it doesn't exist
    if [ ! -f .env ]; then
        cp .env.example .env
        print_info "Created .env from .env.example"
    fi
    
    # Install Python dependencies
    print_info "Installing Python dependencies..."
    if command -v uv &> /dev/null; then
        uv venv
        source .venv/bin/activate
        uv pip install -e ".[dev]"
    else
        print_warning "uv not found, using pip..."
        python -m venv .venv
        source .venv/bin/activate
        pip install -e ".[dev]"
    fi
    
    # Start services
    print_info "Starting Docker services..."
    docker compose up -d
    
    # Wait for services to be ready
    print_info "Waiting for services to be healthy..."
    sleep 5
    
    print_info "Setup complete!"
}

function start() {
    print_info "Starting services..."
    docker compose up -d
    docker compose ps
}

function stop() {
    print_info "Stopping services..."
    docker compose down
}

function restart() {
    stop
    start
}

function logs() {
    docker compose logs -f "${2:-}"
}

function test() {
    print_info "Running tests..."
    source .venv/bin/activate 2>/dev/null || true
    pytest "${@:2}"
}

function format() {
    print_info "Formatting code..."
    source .venv/bin/activate 2>/dev/null || true
    black src/ tests/
    ruff check --fix src/ tests/
}

function api() {
    print_info "Starting API server..."
    source .venv/bin/activate 2>/dev/null || true
    uvicorn src.jelmore.main:app --reload --host 0.0.0.0 --port 8000
}

function shell() {
    print_info "Opening Python shell..."
    source .venv/bin/activate 2>/dev/null || true
    ipython
}

function clean() {
    print_warning "Cleaning up containers and volumes..."
    docker compose down -v
    print_info "Cleanup complete"
}

# Main script logic
case "${1:-help}" in
    setup)
        setup
        ;;
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    logs)
        logs "$@"
        ;;
    test)
        test "$@"
        ;;
    format)
        format
        ;;
    api)
        api
        ;;
    shell)
        shell
        ;;
    clean)
        clean
        ;;
    help|*)
        show_help
        ;;
esac
