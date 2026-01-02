#!/bin/bash
set -e

# --- Configuration ---
VENV_PATH=".venv"

# --- Script Logic ---
echo "--- MDAP Calibration Runner ---"

# Get the directory the script is located in
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 1. Ensure Virtual Environment exists
if [ ! -d "$VENV_PATH" ]; then
    echo "Virtual environment not found. Run ./run.sh first to set it up."
    exit 1
fi

# 3. Run Calibration (pass all arguments through)
echo "Running calibration..."
echo "---"
"$VENV_PATH/bin/python" -m mdap.calibration "$@"
echo "---"

echo "Calibration complete!"
