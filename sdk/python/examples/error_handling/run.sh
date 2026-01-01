#!/bin/bash
set -e

PROJECT_NAME="error_handling"
VENV_PATH="$HOME/virtualenvs/$PROJECT_NAME"

echo "--- Error Handling Demo Runner ---"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

if ! command -v uv &> /dev/null; then
    echo "📥 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "🔧 Ensuring virtual environment at $VENV_PATH..."
mkdir -p "$(dirname "$VENV_PATH")"
if [ ! -d "$VENV_PATH" ]; then
    uv venv "$VENV_PATH"
else
    echo "✅ Virtual environment already exists."
fi

echo "📦 Installing dependencies..."
FLATAGENTS_ROOT="$SCRIPT_DIR/../../../.."
uv pip install --python "$VENV_PATH/bin/python" -e "$FLATAGENTS_ROOT/sdk/python[litellm]"
uv pip install --python "$VENV_PATH/bin/python" -e "$SCRIPT_DIR"

echo "🚀 Running demo..."
echo "---"
"$VENV_PATH/bin/python" -m error_handling.main
echo "---"
echo "✅ Demo complete!"
