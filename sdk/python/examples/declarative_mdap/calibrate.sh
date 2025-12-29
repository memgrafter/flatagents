#!/bin/bash
set -e

# --- Configuration ---
PROJECT_NAME="declarative_mdap"
VENV_PATH="$HOME/virtualenvs/$PROJECT_NAME"

# --- Script Logic ---
echo "--- MDAP Calibration Runner ---"

# Get the directory the script is located in
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 1. Check for LLM API Key
if [ -z "$CEREBRAS_API_KEY" ] && [ -z "$OPENAI_API_KEY" ]; then
    echo "ERROR: No API key found."
    echo "   Please set CEREBRAS_API_KEY or OPENAI_API_KEY:"
    echo "   export CEREBRAS_API_KEY='your-key-here'"
    exit 1
fi

# 2. Ensure Virtual Environment exists
if [ ! -d "$VENV_PATH" ]; then
    echo "Virtual environment not found. Run ./run.sh first to set it up."
    exit 1
fi

# 3. Run Calibration (pass all arguments through)
echo "Running calibration..."
echo "---"
"$VENV_PATH/bin/python" -m declarative_mdap.calibration "$@"
echo "---"

echo "Calibration complete!"
