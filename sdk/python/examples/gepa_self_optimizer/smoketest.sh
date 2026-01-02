#!/bin/bash
# Smoketest for GEPA Self-Optimizer
# Runs with minimal settings to verify everything works end-to-end

set -e

# --- Configuration ---
VENV_PATH=".venv"

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

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"

echo "=============================================="
echo "GEPA Self-Optimizer Smoketest"
echo "=============================================="
echo "Project directory: $PROJECT_DIR"
echo ""

# Change to project directory
cd "$PROJECT_DIR"

# 1. Create Virtual Environment
echo "Ensuring virtual environment..."
if [ ! -d "$VENV_PATH" ]; then
    uv venv "$VENV_PATH"
else
    echo "Virtual environment already exists."
fi

# 3. Install Dependencies
echo "Installing dependencies..."
if [ "$LOCAL_INSTALL" = true ]; then
    echo "  - Installing flatagents from local source..."
    uv pip install --python "$VENV_PATH/bin/python" -e "$SCRIPT_DIR/../..[litellm]"
else
    echo "  - Installing flatagents from PyPI..."
    uv pip install --python "$VENV_PATH/bin/python" "flatagents[litellm]"
fi

# Clean up any previous test data
echo ""
echo "Cleaning up previous test data..."
rm -f "$PROJECT_DIR/data/evaluation_set.json"
rm -rf "$PROJECT_DIR/output/"

echo ""
echo "Step 1: Generate minimal evaluation data"
echo "----------------------------------------------"
"$VENV_PATH/bin/python" main.py generate-data --num-examples 10

echo ""
echo "Step 2: Evaluate baseline judge"
echo "----------------------------------------------"
"$VENV_PATH/bin/python" main.py evaluate

echo ""
echo "Step 3: Run GEPA optimization (minimal settings)"
echo "----------------------------------------------"
"$VENV_PATH/bin/python" main.py run \
    --num-examples 10 \
    --budget 3 \
    --pareto-size 5 \
    --minibatch-size 2 \
    --force-regenerate

echo ""
echo "=============================================="
echo "Smoketest Complete!"
echo "=============================================="
echo ""
echo "Output files:"
ls -la "$PROJECT_DIR/output/" 2>/dev/null || echo "  (no output directory)"
echo ""
echo "To run a full optimization:"
echo "  cd $PROJECT_DIR && .venv/bin/python main.py run --num-examples 100 --budget 50"
