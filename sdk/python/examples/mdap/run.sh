#!/bin/bash
set -e

# --- Configuration ---
PROJECT_NAME="mdap"
VENV_PATH="$HOME/virtualenvs/$PROJECT_NAME"

# --- Script Logic ---
echo "--- MDAP Demo Runner ---"

# Get the directory the script is located in (works from any directory)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 1. Check for LLM API Key
if [ -z "$CEREBRAS_API_KEY" ] && [ -z "$OPENAI_API_KEY" ]; then
    echo "ERROR: No API key found."
    echo "   Please set CEREBRAS_API_KEY or OPENAI_API_KEY:"
    echo "   export CEREBRAS_API_KEY='your-key-here'"
    exit 1
fi

# 2. Create Virtual Environment
echo "Ensuring virtual environment at $VENV_PATH..."
mkdir -p "$(dirname "$VENV_PATH")"
if [ ! -d "$VENV_PATH" ]; then
    uv venv "$VENV_PATH"
else
    echo "Virtual environment already exists."
fi

# 3. Install Dependencies
echo "Installing dependencies..."
echo "  - Installing flatagents..."
uv pip install --python "$VENV_PATH/bin/python" -e "$SCRIPT_DIR/../..[litellm]"

echo "  - Installing mdap package..."
uv pip install --python "$VENV_PATH/bin/python" -e "$SCRIPT_DIR"

# 4. Run the Demo
echo "Running demo..."
echo "---"
"$VENV_PATH/bin/python" -m mdap.demo_machine
echo "---"

echo "Demo complete!"
