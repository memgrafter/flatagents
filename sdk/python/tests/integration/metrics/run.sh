#!/bin/bash
# Metrics Integration Test Runner
# Tests OpenTelemetry metrics with console exporter

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SDK_DIR="$SCRIPT_DIR/../../.."
VENV_PATH="$SCRIPT_DIR/.venv"

# --- Parse Arguments ---
LOCAL_INSTALL=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --local|-l)
            LOCAL_INSTALL=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

echo "Metrics Integration Test"
echo "========================"

# Setup venv with Python 3.12+
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating virtual environment..."
    uv venv "$VENV_PATH" --python python3.12 2>/dev/null || uv venv "$VENV_PATH" --python python3
fi

# Install with metrics extras
echo "Installing flatagents[metrics]..."
if [ "$LOCAL_INSTALL" = true ]; then
    uv pip install --python "$VENV_PATH/bin/python" -e "$SDK_DIR[metrics]" -q
else
    uv pip install --python "$VENV_PATH/bin/python" "flatagents[metrics]" -q
fi

# Run the test
echo "Running metrics tests..."
"$VENV_PATH/bin/python" "$SCRIPT_DIR/test_metrics.py"

echo "Metrics tests passed!"
