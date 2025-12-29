# FlatAgents Python SDK

Reference implementation of the [FlatAgents spec](../../README.md).

## Installation

```bash
pip install flatagents[litellm]   # LiteLLM backend
pip install flatagents[aisuite]   # AISuite backend
pip install flatagents[all]       # Both backends
```

## Usage

### From YAML/JSON Config

```python
from flatagents import DeclarativeAgent

agent = DeclarativeAgent(config_file="agent.yaml")
result = await agent.execute(input={"question": "What is 2+2?"})
```

### From Dictionary

```python
from flatagents import DeclarativeAgent

config = {
    "spec": "declarative_agent",
    "spec_version": "0.4.0",
    "data": {
        "name": "calculator",
        "model": {"provider": "openai", "name": "gpt-4"},
        "system": "You are a calculator.",
        "user": "Calculate: {{ input.expression }}",
        "output": {
            "result": {"type": "float", "description": "The calculated result"}
        }
    }
}

agent = DeclarativeAgent(config_dict=config)
result = await agent.execute(input={"expression": "2 + 2"})
```

### Custom Agent (Subclass FlatAgent)

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

## LLM Backends

Two backends available:

```python
from flatagents import LiteLLMBackend, AISuiteBackend

# LiteLLM - model format: provider/model
backend = LiteLLMBackend(model="openai/gpt-4o", temperature=0.7)

# AISuite - model format: provider:model
backend = AISuiteBackend(model="openai:gpt-4o", temperature=0.7)
```

### Custom Backend

Implement the `LLMBackend` protocol:

```python
class MyBackend:
    total_cost: float = 0.0
    total_api_calls: int = 0

    async def call(self, messages: list, **kwargs) -> str:
        self.total_api_calls += 1
        return "response"

agent = MyAgent(backend=MyBackend())
```

## License

MIT License - see [LICENSE](../../LICENSE) for details.
