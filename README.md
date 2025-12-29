# FlatAgents

A lightweight framework for building LLM-powered agents with pluggable backends.

## Installation

```bash
pip install flatagents[litellm]   # LiteLLM backend
pip install flatagents[aisuite]   # AISuite backend
pip install flatagents[all]       # Both backends
```

Core dependencies: `pyyaml`, `jinja2`

## Components

### FlatAgent

Abstract base class for agents. Subclass and implement:

- `create_initial_state()` - Initialize problem state
- `generate_step_prompt(state)` - Generate user prompt for current state
- `update_state(state, result)` - Apply parsed result to state
- `is_solved(state)` - Check termination condition

### DeclarativeAgent

A FlatAgent configured entirely via YAML or JSON. No code required.

### LLMBackend

Protocol for LLM providers. Two implementations available:

- **`LiteLLMBackend`** - Uses [litellm](https://github.com/BerriAI/litellm). Model format: `provider/model`
- **`AISuiteBackend`** - Uses [aisuite](https://github.com/andrewyng/aisuite). Model format: `provider:model`

```python
from flatagents import LiteLLMBackend, AISuiteBackend

# LiteLLM
backend = LiteLLMBackend(model="openai/gpt-4o", temperature=0.7)

# AISuite (install provider: pip install 'aisuite[openai]')
backend = AISuiteBackend(model="openai:gpt-4o", temperature=0.7)
```

## Usage

### Coded Agent (FlatAgent subclass)

```python
from flatagents import FlatAgent

class MyAgent(FlatAgent):
    def create_initial_state(self):
        return {"count": 0}

    def generate_step_prompt(self, state):
        return f"Count is {state['count']}. What's next?"

    def update_state(self, state, result):
        return {**state, "count": int(result)}

    def is_solved(self, state):
        return state["count"] >= 10

agent = MyAgent(config_file="config.yaml")
trace = await agent.execute()
```

### Flat Agent (YAML-configured)

```python
from flatagents import DeclarativeAgent

agent = DeclarativeAgent(config_file="agent.yaml")
trace = await agent.execute()
```

See `declarative-agent.d.ts` for the full configuration schema.

## On-the-Fly Agent Creation

DeclarativeAgent supports dynamic configuration via `config_dict`, enabling
agents to be created programmatically without filesystem access.

### Direct Dictionary Configuration

```python
from flatagents import DeclarativeAgent

config = {
    "agent": {"name": "dynamic-counter"},
    "model": {
        "provider": "cerebras",
        "name": "zai-glm-4.6",
        "temperature": 0.7
    },
    "state": {
        "initial": {"count": 0, "target": 5}
    },
    "prompts": {
        "system": "You are a counting assistant.",
        "user": "Current count: {{ state.count }}. Target: {{ state.target }}. What's the next number?"
    },
    "parsing": {
        "pattern": "(\\d+)",
        "group": 1,
        "type": "int"
    },
    "state_update": {
        "count": "{{ parsed }}"
    },
    "termination": {
        "condition": "state['count'] >= state['target']"
    }
}

agent = DeclarativeAgent(config_dict=config)
trace = await agent.execute()
```

### Meta-Agent Pattern

An orchestrating agent can generate configurations for sub-agents:

```python
async def run_dynamic_task(task_description: str):
    # Meta-agent generates config based on task
    config = await generate_agent_config(task_description)

    # Instantiate and run the dynamic agent
    agent = DeclarativeAgent(config_dict=config)
    return await agent.execute()
```

### Template-Based Creation

Combine base templates with runtime parameters:

```python
def create_agent(target_string: str, model: str = "openai/gpt-4"):
    return DeclarativeAgent(config_dict={
        "agent": {"name": f"builder-{target_string[:10]}"},
        "model": {"name": model},
        "state": {
            "initial": {"current": "", "target": target_string}
        },
        "prompts": {
            "system": "You build strings character by character.",
            "user": "Target: '{{ state.target }}'. Current: '{{ state.current }}'. Next char?"
        },
        "parsing": {"pattern": '"(.)"'},
        "state_update": {"current": "state['current'] + parsed"},
        "termination": {"condition": "state['current'] == state['target']"}
    })

agent = create_agent("Hello!")
trace = await agent.execute()
```

### Serialization for Later Use

Configs can be stored and retrieved:

```python
import json

# Store config
config = {...}
with open("stored_agent.json", "w") as f:
    json.dump(config, f)

# Later: load and instantiate
agent = DeclarativeAgent(config_file="stored_agent.json")
```

## Configuration Reference

### Model Configuration

```yaml
model:
  name: "gpt-4"
  provider: "openai"      # Combined as "openai/gpt-4"
  temperature: 0.7
  max_tokens: 2048
  retry_delays: [1, 2, 4, 8]
```

### State Configuration

```yaml
state:
  initial:
    count: 0
    items: []
  complexity: 10          # Or expression: "len(state['items'])"
```

### Prompts Configuration

```yaml
prompts:
  system: "You are a helpful assistant."
  user: |
    Current state: {{ state.count }}
    What should we do next?
  post_history_instruction: "Respond with only a number."
```

### Parsing Configuration

Single-field parsing (simple):

```yaml
parsing:
  pattern: "(\\d+)"       # Regex with capture group
  group: 1                # Which group to extract
  type: "int"             # Convert to: str, int, float, bool
```

Multi-field parsing (for structured outputs):

```yaml
parsing:
  fields:
    move:
      pattern: "move\\s*=\\s*(\\[\\d+,\\s*\\d+,\\s*\\d+\\])"
      type: "json"
    next_state:
      pattern: "next_state\\s*=\\s*(\\[\\[.*?\\]\\])"
      type: "json"
```

Supported types: `str`, `int`, `float`, `bool`, `json`

### Validation Configuration

Validate parsed results with Python expressions:

```yaml
validation:
  - "len(parsed.get('move', [])) == 3"
  - "parsed['move'][0] >= 1"
  - "0 <= parsed['move'][1] <= 2"
```

All rules must evaluate to `True` for the response to be accepted.
Available variable: `parsed` (the parsed result dict).

### State Update Configuration

```yaml
state_update:
  count: "{{ parsed }}"                    # Jinja2 template
  total: "state['total'] + parsed"         # Python expression
  done: true                               # Literal value
```

### Termination Configuration

```yaml
termination:
  condition: "state['count'] >= 10"        # Python expression
```

## Custom LLM Backends

Implement the `LLMBackend` protocol:

```python
from flatagents import FlatAgent, LLMBackend

class MyBackend:
    total_cost: float = 0.0
    total_api_calls: int = 0

    async def call(self, messages: list, **kwargs) -> str:
        # Your LLM call logic here
        self.total_api_calls += 1
        return "response"

agent = MyAgent(backend=MyBackend())
```

## License

MIT License - see [LICENSE](LICENSE) for details.
