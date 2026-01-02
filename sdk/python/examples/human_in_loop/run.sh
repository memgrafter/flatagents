#!/bin/bash
set -e

# --- Configuration ---
PROJECT_NAME="human_in_loop"
VENV_PATH="$HOME/virtualenvs/$PROJECT_NAME"

# --- Script Logic ---
echo "--- Human-in-the-Loop Demo Runner ---"

# Get the directory the script is located in
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to the script's directory
cd "$SCRIPT_DIR"

# 1. Create Virtual Environment
echo "Ensuring virtual environment at $VENV_PATH..."
mkdir -p "$(dirname "$VENV_PATH")"
if [ ! -d "$VENV_PATH" ]; then
    uv venv "$VENV_PATH"
else
    echo "Virtual environment already exists."
fi

# 2. Install Dependencies
echo "Installing dependencies..."
echo "  - Installing flatagents..."
uv pip install --python "$VENV_PATH/bin/python" -e "$SCRIPT_DIR/../..[litellm]"

echo "  - Installing human_in_loop package..."
uv pip install --python "$VENV_PATH/bin/python" -e "$SCRIPT_DIR"

# 3. Run the Demo
echo "Running demo..."
echo "---"
"$VENV_PATH/bin/python" -m human_in_loop.main "$@"
echo "---"

echo "Demo complete!"
