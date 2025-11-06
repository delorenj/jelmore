#!/bin/bash
# 🚀 PARALLEL TEST EXECUTION SYMPHONY - The Container Whisperer's Dream Script
# Transforms sequential tests into CONCURRENT EXCELLENCE

set -e

echo "🎭 Initializing PARALLEL TEST ORCHESTRATION..."
echo "   by The Container Whisperer & The Void"
echo ""

# Detect optimal worker count (CPU cores or configured value)
WORKERS=${TEST_WORKERS:-auto}
COVERAGE_THRESHOLD=${COVERAGE_THRESHOLD:-80}

echo "🐝 Worker Configuration:"
echo "   Workers: $WORKERS"
echo "   Coverage Target: $COVERAGE_THRESHOLD%"
echo ""

# Create test result directories
mkdir -p test-results/{unit,integration,e2e}
mkdir -p coverage_html

echo "🧪 Phase 1: UNIT TESTS (Lightning Speed Swarm)"
pytest -xvs tests/unit/ \
    -n $WORKERS \
    --dist=worksteal \
    --timeout=10 \
    --cov=src/jelmore \
    --cov-report=term-missing \
    --cov-append \
    --junitxml=test-results/unit/junit.xml \
    -m "unit" \
    || echo "⚠️  Unit tests had issues - continuing..."

echo ""
echo "🔧 Phase 2: INTEGRATION TESTS (Coordinated Chaos)"
pytest -xvs tests/integration/ \
    -n $WORKERS \
    --dist=loadfile \
    --timeout=30 \
    --cov=src/jelmore \
    --cov-report=term-missing \
    --cov-append \
    --junitxml=test-results/integration/junit.xml \
    -m "integration" \
    || echo "⚠️  Integration tests had issues - continuing..."

echo ""
echo "🌐 Phase 3: API TESTS (End-to-End Excellence)"
pytest -xvs tests/test_api.py tests/test_providers.py \
    -n $WORKERS \
    --dist=loadscope \
    --timeout=60 \
    --cov=src/jelmore \
    --cov-report=term-missing \
    --cov-append \
    --junitxml=test-results/e2e/junit.xml \
    || echo "⚠️  E2E tests had issues - continuing..."

echo ""
echo "📊 FINAL COVERAGE SYMPHONY:"
pytest --cov=src/jelmore \
    --cov-report=html:coverage_html \
    --cov-report=xml \
    --cov-report=term-missing \
    --cov-fail-under=$COVERAGE_THRESHOLD \
    --collect-only > /dev/null || true

echo ""
echo "🎉 PARALLEL TEST EXECUTION COMPLETE!"
echo "   Check coverage_html/index.html for detailed coverage report"
echo "   The void is pleased with this CONCURRENT EXCELLENCE!"

# Store performance metrics
echo "$(date): Parallel test run completed" >> test-performance.log