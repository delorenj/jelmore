#!/usr/bin/env zsh
"""
Quick start script for Jelmore
"""

echo "🚀 Starting Jelmore..."

# Check if docker services are running
echo "📦 Checking Docker services..."
if ! docker-compose ps | grep -q "Up"; then
    echo "Starting Docker services..."
    docker-compose up -d
    echo "Waiting for services to be healthy..."
    sleep 5
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "🐍 Creating virtual environment..."
    uv venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install dependencies if needed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "📚 Installing dependencies..."
    uv pip install -e ".[dev]"
fi

# Copy env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️ Creating .env file..."
    cp .env.example .env
fi

# Run migrations (once we add Alembic)
# alembic upgrade head

echo "✅ Starting Jelmore server..."
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
