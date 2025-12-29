# DeclarativeAgent HelloWorld Demo

A simple "Hello, World!" project that demonstrates how to use the `flatagents` library.

The demo involves an agent that attempts to build the string "Hello, World!" by querying an LLM one character at a time. It showcases the core components of the library, including:
- Using a `DeclarativeAgent` from YAML configuration.
- Tracking execution statistics like cost and API calls.

## Prerequisites

1.  **Python & `uv`**: Ensure you have Python 3.10+ and the `uv` package manager installed.
2.  **LLM API Key**: An active API key is required. The demo checks for `OPENAI_API_KEY` or `CEREBRAS_API_KEY` environment variables.

## Quick Start (with `run.sh`)

The fastest way to run the demo is with the provided shell script, which handles all setup for you.

```bash
# Set your API key
export OPENAI_API_KEY="your-api-key-here"

# Make the script executable (if you haven't already)
chmod +x run.sh

# Run the demo
./run.sh
```

## Manual Setup

If you prefer to set up the environment manually:

1.  **Navigate into this project directory**:
    ```bash
    cd examples/declarativeagent_helloworld
    ```
2.  **Install dependencies** using `uv`:
    ```bash
    uv venv
    uv pip install -e .
    ```
3.  **Set your LLM API key**:
    ```bash
    export OPENAI_API_KEY="your-api-key-here"
    ```
4.  **Run the demo**:
    ```bash
    uv run python -m declarativeagent_helloworld.main
    ```
