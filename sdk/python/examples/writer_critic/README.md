# Writer-Critic Demo

A multi-agent example demonstrating iterative refinement using the `flatagents` library.

This demo showcases:
- Two `DeclarativeAgent` instances working together
- An iterative feedback loop between agents
- Using Jinja2 templates for conditional prompts

## How It Works

1. **Writer Agent**: Generates marketing taglines for a product
2. **Critic Agent**: Evaluates taglines and provides feedback with a score
3. **Iteration**: The writer revises based on feedback until the target score is reached

## Prerequisites

1. **Python & `uv`**: Ensure you have Python 3.10+ and the `uv` package manager installed.
2. **LLM API Key**: An active API key is required. The demo checks for `OPENAI_API_KEY` or `CEREBRAS_API_KEY` environment variables.

## Quick Start (with `run.sh`)

The fastest way to run the demo is with the provided shell script:

```bash
# Set your API key
export CEREBRAS_API_KEY="your-api-key-here"

# Make the script executable (if you haven't already)
chmod +x run.sh

# Run the demo
./run.sh
```

## Manual Setup

If you prefer to set up the environment manually:

1. **Navigate into this project directory**:
    ```bash
    cd examples/writer_critic
    ```
2. **Install dependencies** using `uv`:
    ```bash
    uv venv
    uv pip install -e .
    ```
3. **Set your LLM API key**:
    ```bash
    export CEREBRAS_API_KEY="your-api-key-here"
    ```
4. **Run the demo**:
    ```bash
    uv run python -m writer_critic.main
    ```

## Example Output

```
============================================================
Writer-Critic Demo
============================================================

Writer Agent: writer
Writer Model: cerebras/zai-glm-4.6
Critic Agent: critic
Critic Model: cerebras/zai-glm-4.6

Product: a CLI tool for AI agents
Target Score: 8/10
Max Rounds: 4

------------------------------------------------------------

Generating initial tagline...

Initial tagline: "Command Your AI, One Line at a Time"

--- Round 1 ---
Score: 7/10
Feedback: Good rhythm but could be more specific about the value proposition.

Revising tagline...
New tagline: "Build Smarter Agents, Faster - From Your Terminal"

--- Round 2 ---
Score: 8/10
Feedback: Clear value prop, good technical appeal.

Target score reached!

============================================================
RESULTS
============================================================

Final Tagline: "Build Smarter Agents, Faster - From Your Terminal"
Final Score: 8/10
Rounds: 2

--- Statistics ---
Writer API calls: 2
Critic API calls: 2
Total API calls: 4
Estimated cost: $0.0012
```

## Agent Configurations

- `config/writer.yml`: Writer agent with higher temperature (0.8) for creativity
- `config/critic.yml`: Critic agent with lower temperature (0.3) for consistent evaluation
