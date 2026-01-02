# Creating Examples

Guide for creating new flatagents examples.

## Required Structure

```
example_name/
├── config/
│   ├── machine.yml      # FlatMachine config (required)
│   └── *.yml            # FlatAgent configs (one per agent)
├── src/
│   └── example_name/    # Package name = example folder name
│       ├── __init__.py  # """Example Name for FlatAgents."""
│       ├── main.py      # Entry point with main() function
│       └── hooks.py     # Optional: custom MachineHooks
├── pyproject.toml
├── run.sh
├── README.md
└── .gitignore
```

## File Templates

### pyproject.toml

```toml
[project]
name = "example_name"
version = "0.1.0"
description = "Short description for FlatAgents"
dependencies = ["flatagents[litellm]"]
requires-python = ">=3.10"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.metadata]
allow-direct-references = true

[project.scripts]
example-name-demo = "example_name.main:main"
```

### run.sh

```bash
#!/bin/bash
set -e

PROJECT_NAME="example_name"
VENV_PATH="$HOME/virtualenvs/$PROJECT_NAME"

echo "--- Example Name Demo Runner ---"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Create venv
mkdir -p "$(dirname "$VENV_PATH")"
if [ ! -d "$VENV_PATH" ]; then
    uv venv "$VENV_PATH"
fi

# Install
uv pip install --python "$VENV_PATH/bin/python" -e "$SCRIPT_DIR/../..[litellm]"
uv pip install --python "$VENV_PATH/bin/python" -e "$SCRIPT_DIR"

# Run
"$VENV_PATH/bin/python" -m example_name.main "$@"
```

**Important:** Run `chmod +x run.sh` after creating.

### .gitignore

```
.venv/
uv.lock
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.DS_Store
.env
```

### src/example_name/__init__.py

```python
"""Example Name for FlatAgents."""
```

### src/example_name/main.py

```python
"""
Example Name Demo for FlatAgents.

Brief description of what this example demonstrates.

Usage:
    python -m example_name.main
    ./run.sh
"""

import asyncio
import logging
from pathlib import Path

from flatagents import FlatMachine, LoggingHooks
# from .hooks import CustomHooks  # If using custom hooks

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


async def run():
    config_path = Path(__file__).parent.parent.parent / 'config' / 'machine.yml'
    machine = FlatMachine(config_file=str(config_path), hooks=LoggingHooks())
    
    result = await machine.execute(input={...})
    
    print(f"Result: {result}")
    print(f"API calls: {machine.total_api_calls}, Cost: ${machine.total_cost:.4f}")
    return result


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

### config/machine.yml

```yaml
spec: flatmachine
spec_version: "0.1.0"

data:
  name: example-name
  
  context:
    key: "{{ input.key }}"
  
  agents:
    agent_name: ./agent.yml
  
  states:
    start:
      type: initial
      transitions:
        - to: process
    
    process:
      agent: agent_name
      input:
        key: "{{ context.key }}"
      output_to_context:
        result: "{{ output.result }}"
      transitions:
        - to: done
    
    done:
      type: final
      output:
        result: "{{ context.result }}"

metadata:
  description: "Brief description"
```

### config/agent.yml

```yaml
spec: flatagent
spec_version: "0.1.0"

data:
  name: agent-name
  
  model:
    provider: cerebras
    name: zai-glm-4.6
    temperature: 0.6
  
  system_prompt: |
    System instructions here.
  
  user_prompt: |
    User prompt with {{ variable }} templating.
  
  output_schema:
    type: object
    properties:
      result:
        type: string
    required: [result]

metadata:
  description: "Brief description"
```

## Custom Hooks (Optional)

For human-in-loop, voting, or custom logic:

```python
# src/example_name/hooks.py
from typing import Any, Dict
from flatagents import MachineHooks


class CustomHooks(MachineHooks):
    def on_action(self, action_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        if action_name == "custom_action":
            # Custom logic here
            context["custom_result"] = "value"
        return context
```

Reference in machine.yml:
```yaml
states:
  custom_state:
    action: custom_action  # Triggers on_action hook
```

## Hook Methods

| Method | When Called | Use Case |
|--------|-------------|----------|
| `on_machine_start(context)` | Execution begins | Init logging/metrics |
| `on_machine_end(context, output)` | Execution ends | Cleanup, final logging |
| `on_state_enter(state, context)` | Before state executes | Pre-processing |
| `on_state_exit(state, context, output)` | After state executes | Post-processing |
| `on_transition(from, to, context)` | Between states | Override transitions |
| `on_error(state, error, context)` | Error occurs | Recovery routing |
| `on_action(action, context)` | State has `action:` | Custom logic |

## Checklist

- [ ] Folder name = package name (use underscores)
- [ ] `config/machine.yml` with `spec: flatmachine`
- [ ] At least one `config/*.yml` agent
- [ ] `src/example_name/__init__.py` with docstring
- [ ] `src/example_name/main.py` with `main()` function
- [ ] `pyproject.toml` with correct name
- [ ] `run.sh` executable (`chmod +x`)
- [ ] `.gitignore`
- [ ] `README.md` explaining the example
