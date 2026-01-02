#!/bin/bash
# Integration Test Runner
# Runs all integration tests in isolated virtual environments

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=============================================="
echo "FlatAgents Integration Tests"
echo "=============================================="
echo ""

# Track results
PASSED=0
FAILED=0
FAILED_TESTS=""

# Find and run all test suites
for test_dir in "$SCRIPT_DIR"/*/; do
    if [ -f "$test_dir/run.sh" ]; then
        test_name=$(basename "$test_dir")
        echo "Running: $test_name"
        echo "----------------------------------------------"
        
        if "$test_dir/run.sh"; then
            echo "✓ $test_name PASSED"
            ((PASSED++))
        else
            echo "✗ $test_name FAILED"
            ((FAILED++))
            FAILED_TESTS="$FAILED_TESTS $test_name"
        fi
        echo ""
    fi
done

# Summary
echo "=============================================="
echo "Results: $PASSED passed, $FAILED failed"
echo "=============================================="

if [ $FAILED -gt 0 ]; then
    echo "Failed tests:$FAILED_TESTS"
    exit 1
fi

echo "All integration tests passed!"
