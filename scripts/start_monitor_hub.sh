#!/bin/bash
set -e

# Start Monitor Hub Script
echo "🐝 Starting Jelmore Pipeline Monitor Hub..."

# Change to project directory
cd "$(dirname "$0")/.."

# Check if Python environment is available
if [ -f ".venv/bin/activate" ]; then
    echo "📦 Activating Python virtual environment..."
    source .venv/bin/activate
else
    echo "⚠️  No virtual environment found, using system Python"
fi

# Install required dependencies if needed
echo "🔧 Checking dependencies..."
pip install -q aiohttp nats-py structlog

# Run coordination hooks
echo "🔗 Initializing coordination hooks..."
npx claude-flow@alpha hooks pre-task --description "Pipeline monitor hub startup" || true
npx claude-flow@alpha hooks session-restore --session-id "monitor-hub-$(date +%s)" || true

# Store startup event in memory
npx claude-flow@alpha hooks notify \
    --message "Pipeline Monitor Hub starting" \
    --memory-key "hive/monitor/startup" \
    --telemetry true || true

# Start the monitor hub
echo "🚀 Launching Pipeline Monitor Hub..."
python3 monitoring/pipeline_monitor_hub.py

# Cleanup hooks on exit
echo "🧹 Running cleanup hooks..."
npx claude-flow@alpha hooks post-task --task-id "monitor-hub" --analyze-performance true || true
npx claude-flow@alpha hooks session-end --export-metrics true || true