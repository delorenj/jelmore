#!/bin/bash
# 📊 PARALLEL COVERAGE ANALYSIS - The Container Whisperer's Data Symphony
# Comprehensive coverage analysis with parallel execution

set -e

echo "📊 COMPREHENSIVE COVERAGE ANALYSIS INITIATED!"
echo "   Parallel execution meets data-driven excellence"
echo ""

# Configuration
WORKERS=${TEST_WORKERS:-auto}
MIN_COVERAGE=${MIN_COVERAGE:-80}
TARGET_COVERAGE=${TARGET_COVERAGE:-90}

# Clean previous results
rm -rf coverage_html/ .coverage*
mkdir -p coverage_html reports

echo "🧮 Phase 1: Parallel test execution with coverage tracking..."
pytest \
    -n $WORKERS \
    --dist=worksteal \
    --cov=src/jelmore \
    --cov-branch \
    --cov-report=term-missing \
    --cov-report=html:coverage_html \
    --cov-report=xml:reports/coverage.xml \
    --cov-report=json:reports/coverage.json \
    --timeout=30 \
    --tb=short \
    tests/ \
    || echo "⚠️  Some tests failed - coverage data still collected"

echo ""
echo "📈 Phase 2: Coverage analysis and reporting..."

# Generate detailed coverage report
python3 -c "
import json
import sys
from pathlib import Path

try:
    with open('reports/coverage.json', 'r') as f:
        coverage_data = json.load(f)
    
    total_coverage = coverage_data['totals']['percent_covered']
    
    print(f'📊 COVERAGE ANALYSIS RESULTS:')
    print(f'   Total Coverage: {total_coverage:.1f}%')
    print(f'   Target: {$TARGET_COVERAGE}%')
    print(f'   Minimum: {$MIN_COVERAGE}%')
    print()
    
    if total_coverage >= $TARGET_COVERAGE:
        print('🎉 EXCELLENT! Target coverage achieved!')
        print('   The void is pleased with this thoroughness!')
    elif total_coverage >= $MIN_COVERAGE:
        print('✅ Good coverage achieved!')
        print(f'   Aim for {$TARGET_COVERAGE}% for excellence!')
    else:
        print('⚠️  Coverage below minimum threshold!')
        print('   More tests needed for CONCURRENT EXCELLENCE!')
        sys.exit(1)
    
    print()
    print('📁 Detailed reports available at:')
    print('   HTML: coverage_html/index.html')
    print('   XML:  reports/coverage.xml')
    print('   JSON: reports/coverage.json')

except FileNotFoundError:
    print('⚠️  Coverage data not found - tests may have failed')
    sys.exit(1)
"

echo ""
echo "🔍 Phase 3: Coverage gap analysis..."
python3 -c "
import json
from pathlib import Path

try:
    with open('reports/coverage.json', 'r') as f:
        data = json.load(f)
    
    print('📋 Files needing attention (< 80% coverage):')
    files_to_improve = []
    
    for file_path, file_data in data['files'].items():
        coverage = file_data['summary']['percent_covered']
        if coverage < 80:
            files_to_improve.append((file_path, coverage))
            print(f'   {file_path}: {coverage:.1f}%')
    
    if not files_to_improve:
        print('   🎉 All files have good coverage!')
    
    print()
    print(f'📊 Summary: {len(files_to_improve)} files need improvement')

except (FileNotFoundError, KeyError) as e:
    print(f'⚠️  Error analyzing coverage: {e}')
"

echo ""
echo "📊 PARALLEL COVERAGE ANALYSIS COMPLETE!"
echo "   Open coverage_html/index.html for interactive report"
echo "   The Container Whisperer approves of this DATA-DRIVEN EXCELLENCE!"