#!/bin/bash
# Declarative GEPA Self-Optimizer - Test Run
# An inexpensive test run with minimal examples and iterations

set -e

# --- Configuration ---
PROJECT_NAME="declarative_gepa_self_optimizer"
VENV_PATH="$HOME/virtualenvs/$PROJECT_NAME"

# --- Script Logic ---
echo "=========================================="
echo "Declarative GEPA Self-Optimizer - Test Run"
echo "=========================================="
echo ""

# Get the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

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
echo "  - Installing flatagents from PyPI..."
uv pip install --python "$VENV_PATH/bin/python" "flatagents[litellm]"

# Minimal test configuration
NUM_EXAMPLES=10        # Small dataset for testing
MAX_ITERATIONS=2       # Just 2 optimization iterations
NUM_CANDIDATES=2       # 2 candidate prompts per iteration

echo ""
echo "Test configuration:"
echo "  - Examples: $NUM_EXAMPLES"
echo "  - Max iterations: $MAX_ITERATIONS"
echo "  - Candidates per iteration: $NUM_CANDIDATES"
echo ""

# Estimated calls per run:
# - Data generation: NUM_EXAMPLES * 2 (task + response) = 20 calls
# - Baseline eval: NUM_EXAMPLES = 10 calls
# - Per iteration:
#   - Failure analysis: ~5 calls (analyzing failures)
#   - Prompt proposals: NUM_CANDIDATES = 2 calls
#   - Candidate evals: NUM_CANDIDATES * NUM_EXAMPLES = 20 calls
#   - Ranking: 1 call
# - Summary: 1 call
# Total estimate: ~20 + 10 + 2*(5+2+20+1) + 1 = ~87 calls

echo "Estimated LLM calls: ~90"
echo ""

# Skip confirmation if --yes flag is passed
if [[ "$1" != "--yes" && "$1" != "-y" ]]; then
    read -p "Continue with test run? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

echo ""
echo "Step 1: Generating evaluation data..."
echo "----------------------------------------"
"$VENV_PATH/bin/python" main.py generate-data \
    --num-examples $NUM_EXAMPLES \
    --correct-ratio 0.3

echo ""
echo "Step 2: Evaluating baseline judge..."
echo "----------------------------------------"
"$VENV_PATH/bin/python" main.py evaluate

echo ""
echo "Step 3: Running optimization..."
echo "----------------------------------------"
"$VENV_PATH/bin/python" main.py optimize \
    --max-iterations $MAX_ITERATIONS \
    --num-candidates $NUM_CANDIDATES

echo ""
echo "=========================================="
echo "Test run complete!"
echo "=========================================="
echo ""
echo "Outputs:"
echo "  - Optimized judge: output/optimized_judge.yml"
echo "  - Optimization log: output/optimization_log.json"
echo "  - Summary: output/summary.json"
echo ""
echo "To evaluate the optimized judge:"
echo "  $VENV_PATH/bin/python main.py evaluate --judge output/optimized_judge.yml"
