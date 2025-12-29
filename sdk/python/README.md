# FlatAgents Python SDK

**Status: Prototype**

Python SDK for [FlatAgents](https://github.com/memgrafter/flatagents)—a declarative format for defining AI agents. Write your agent config once, run it anywhere. See the [spec](https://github.com/memgrafter/flatagents/blob/main/declarative-agent.d.ts).

### In Progress

- [ ] Unify input/output adapters for agent chaining
- [ ] Simplify output adapters
- [ ] Add declarative workflows (flatworkflows)
- [ ] Add examples
- [ ] TypeScript SDK

## Why FlatAgents?

Agent configs are portable. Write your agent YAML once, run it with any SDK that implements the spec. Share agents across teams, languages, and frameworks. Want an SDK for your language? [Build one](https://github.com/memgrafter/flatagents)—the spec is simple.

## Agent Definition

Define agents in YAML or JSON. Both formats are first-class.

**agent.yml**
```yaml
spec: declarative_agent
spec_version: "0.4.0"

data:
  name: summarizer
  model:
    provider: openai
    name: gpt-4o-mini
  system: You summarize text concisely.
  user: "Summarize this: {{ input.text }}"
  output:
    summary:
      type: str
      description: A concise summary
```

**agent.json**
```json
{
  "spec": "declarative_agent",
  "spec_version": "0.4.0",
  "data": {
    "name": "summarizer",
    "model": {
      "provider": "openai",
      "name": "gpt-4o-mini"
    },
    "system": "You summarize text concisely.",
    "user": "Summarize this: {{ input.text }}",
    "output": {
      "summary": {
        "type": "str",
        "description": "A concise summary"
      }
    }
  }
}
```

```python
from flatagents import DeclarativeAgent

agent = DeclarativeAgent(config_file="agent.yml")  # or agent.json
result = await agent.execute(input={"text": "Long article here..."})
print(result["summary"])
```

## Quick Start

```bash
pip install flatagents[litellm]
```

**writer.yaml**
```yaml
spec: declarative_agent
spec_version: "0.4.0"

data:
  name: writer
  model:
    provider: openai
    name: gpt-4o-mini
  system: You write short, punchy marketing copy.
  user: |
    Product: {{ input.product }}
    {% if input.feedback %}Previous attempt: {{ input.tagline }}
    Feedback: {{ input.feedback }}
    Write an improved tagline.{% else %}Write a tagline.{% endif %}
  output:
    tagline:
      type: str
      description: The tagline
```

**critic.yaml**
```yaml
spec: declarative_agent
spec_version: "0.4.0"

data:
  name: critic
  model:
    provider: openai
    name: gpt-4o-mini
  system: You critique marketing copy. Be constructive but direct.
  user: |
    Product: {{ input.product }}
    Tagline: {{ input.tagline }}
  output:
    feedback:
      type: str
      description: Constructive feedback
    score:
      type: int
      description: Score from 1-10
```

**run.py**
```python
import asyncio
from flatagents import DeclarativeAgent

async def main():
    writer = DeclarativeAgent(config_file="writer.yaml")
    critic = DeclarativeAgent(config_file="critic.yaml")

    product = "a CLI tool for AI agents"
    draft = await writer.execute(input={"product": product})

    for round in range(4):
        review = await critic.execute(input={"product": product, **draft})
        print(f"Round {round + 1}: \"{draft['tagline']}\" - {review['score']}/10")

        if review["score"] >= 8:
            break
        draft = await writer.execute(input={"product": product, **review, **draft})

    print(f"Final: {draft['tagline']}")

asyncio.run(main())
```

```bash
export OPENAI_API_KEY="your-key"
python run.py
```

## Usage

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
