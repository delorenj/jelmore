#!/bin/bash
# ⚡ RAPID FEEDBACK TEST EXECUTION - For When You Need Speed of Light Results
# The Container Whisperer's Emergency Response System

set -e

echo "⚡ RAPID FEEDBACK MODE ACTIVATED!"
echo "   Testing only what matters, testing it FAST!"
echo ""

# Quick smoke tests with maximum parallelization
WORKERS=${TEST_WORKERS:-auto}

echo "🏃‍♂️ Running LIGHTNING-FAST unit tests..."
pytest tests/unit/ \
    -n $WORKERS \
    --dist=worksteal \
    --timeout=5 \
    --tb=line \
    --quiet \
    -x \
    --disable-warnings \
    -m "unit and not slow" \
    || exit 1

echo ""
echo "🔍 Quick integration smoke tests..."
pytest tests/integration/ \
    -n $WORKERS \
    --dist=loadfile \
    --timeout=10 \
    --tb=line \
    --quiet \
    -x \
    --disable-warnings \
    -k "not slow" \
    --maxfail=3 \
    || echo "⚠️  Some integration tests failed - check with full suite"

echo ""
echo "🎯 API endpoint validation..."
pytest tests/test_api.py \
    -n $WORKERS \
    --dist=loadscope \
    --timeout=15 \
    --tb=line \
    --quiet \
    -x \
    --disable-warnings \
    -k "test_health or test_create or test_status" \
    || echo "⚠️  Core API tests failed - needs attention"

echo ""
echo "⚡ RAPID FEEDBACK COMPLETE!"
echo "   For full results, run: ./scripts/test-parallel.sh"
echo "   The void approves of this SPEED-OF-LIGHT efficiency!"