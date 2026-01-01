#!/bin/bash
set -e

# --- Configuration ---
PROJECT_NAME="flatagent_helloworld"
VENV_PATH="$HOME/virtualenvs/$PROJECT_NAME"

# --- Script Logic ---
echo "--- FlatAgent HelloWorld Demo Runner ---"

# Get the directory the script is located in
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to the script's directory so `uv` can find pyproject.toml
cd "$SCRIPT_DIR"

# 0. Ensure uv is installed
if ! command -v uv &> /dev/null; then
    echo "📥 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# 1. Check for LLM API Key
if [ -z "$CEREBRAS_API_KEY" ] && [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ ERROR: No API key found."
    echo "   Please set CEREBRAS_API_KEY or OPENAI_API_KEY:"
    echo "   export CEREBRAS_API_KEY='your-key-here'"
    exit 1
fi

# 2. Create Virtual Environment
echo "🔧 Ensuring virtual environment at $VENV_PATH..."
mkdir -p "$(dirname "$VENV_PATH")"
if [ ! -d "$VENV_PATH" ]; then
    uv venv "$VENV_PATH"
else
    echo "✅ Virtual environment already exists."
fi

# 3. Install Dependencies
echo "📦 Installing dependencies..."
echo "  - Installing flatagents from local source..."
# Install local flatagents with litellm extra
FLATAGENTS_ROOT="$SCRIPT_DIR/../../../.."
uv pip install --python "$VENV_PATH/bin/python" -e "$FLATAGENTS_ROOT/sdk/python[litellm]"

echo "  - Installing helloworld demo package..."
uv pip install --python "$VENV_PATH/bin/python" -e "$SCRIPT_DIR"

# 4. Run the Demo
echo "🚀 Running demo..."
echo "---"
"$VENV_PATH/bin/python" -m flatagent_helloworld.main
echo "---"

echo "✅ Demo complete!"
