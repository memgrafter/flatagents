# FlatAgents

A declarative specification for LLM-powered agents. Define agents in YAML/JSON, run them anywhere.

- **Orchestrate via code or existing orchestration** - FlatAgents defines single agents, not workflows. Compose them using your language of choice or plug into existing orchestration frameworks.
- **Use LLM-assisted coding to define your agent YAMLs** - For best results, let an LLM help you write and iterate on agent configurations.

## The Spec

An agent is a single LLM call: **model + prompts + output schema**. That's it.

See [`declarative-agent.d.ts`](./declarative-agent.d.ts) for the full TypeScript schema.

### Structure

```yaml
spec: declarative_agent
spec_version: "0.4.0"

data:
  name: my-agent
  model: { ... }
  system: "..."
  user: "..."
  output: { ... }

metadata:
  description: "Optional metadata"
  tags: ["example"]
```

### Example Agent

Define agents in YAML or JSON—both are first-class.

**critic.yml**
```yaml
spec: declarative_agent
spec_version: "0.4.0"

data:
  name: critic

  model:
    provider: cerebras
    name: zai-glm-4.6
    temperature: 0.5

  system: |
    Act as a ruthless critic. Analyze drafts for errors.
    Rate severity as: High, Medium, or Low.

  user: |
    Question: {{ input.question }}
    Draft: {{ input.draft }}

  output:
    critique:
      type: str
      description: "Specific errors found in the draft"
    severity:
      type: str
      description: "Error severity"
      enum: ["High", "Medium", "Low"]

metadata:
  description: "Critiques draft answers"
  tags: ["reflection", "qa"]
```

**critic.json**
```json
{
  "spec": "declarative_agent",
  "spec_version": "0.4.0",
  "data": {
    "name": "critic",
    "model": {
      "provider": "cerebras",
      "name": "zai-glm-4.6",
      "temperature": 0.5
    },
    "system": "Act as a ruthless critic. Analyze drafts for errors.\nRate severity as: High, Medium, or Low.",
    "user": "Question: {{ input.question }}\nDraft: {{ input.draft }}",
    "output": {
      "critique": {
        "type": "str",
        "description": "Specific errors found in the draft"
      },
      "severity": {
        "type": "str",
        "description": "Error severity",
        "enum": ["High", "Medium", "Low"]
      }
    }
  },
  "metadata": {
    "description": "Critiques draft answers",
    "tags": ["reflection", "qa"]
  }
}
```

## Configuration Reference

### Model Configuration

```yaml
model:
  name: "gpt-4"              # Model name
  provider: "openai"         # Provider (openai, anthropic, cerebras, etc.)
  temperature: 0.7           # Sampling temperature (0.0 to 2.0)
  max_tokens: 2048           # Maximum tokens to generate
  top_p: 1.0                 # Nucleus sampling parameter
  frequency_penalty: 0.0     # Frequency penalty (-2.0 to 2.0)
  presence_penalty: 0.0      # Presence penalty (-2.0 to 2.0)
```

### Prompts (Jinja2 Templates)

Prompts use Jinja2 templating. Available variables:
- `input.*` - Values passed to the agent at runtime

```yaml
system: |
  You are a helpful assistant specialized in {{ input.domain }}.

user: |
  Question: {{ input.question }}
  Context: {{ input.context }}

instruction_suffix: "Respond in JSON format."  # Optional, appended after user prompt
```

### Output Schema

Declares expected output fields. The runtime decides how to extract them (structured output, tool calls, regex, etc.)

```yaml
output:
  answer:
    type: str
    description: "The answer to the question"

  confidence:
    type: float
    description: "Confidence score"

  category:
    type: str
    description: "Answer category"
    enum: ["factual", "opinion", "unknown"]

  sources:
    type: list
    items:
      type: str
    description: "List of sources"

  metadata:
    type: object
    properties:
      reasoning:
        type: str
      tokens_used:
        type: int
```

**Supported types:** `str`, `int`, `float`, `bool`, `json`, `list`, `object`

### Metadata

Extensibility layer. Runners ignore unrecognized keys.

```yaml
metadata:
  description: "What this agent does"
  tags: ["category", "type"]
  author: "name"
  # Add any custom fields
```

## Reference SDKs

| SDK | Package | Status |
|-----|---------|--------|
| [Python](./sdk/python) | `pip install flatagents` | Available |
| [JavaScript](./sdk/js) | `npm install flatagents` | Coming soon |

### Python Quick Start

```bash
pip install flatagents[litellm]
```

```python
from flatagents import DeclarativeAgent

agent = DeclarativeAgent(config_file="agent.yaml")
result = await agent.execute(input={"question": "What is 2+2?"})
```

### JavaScript Quick Start

Coming soon.

## Design Principles

1. **Declarative over imperative** - Define what you want, not how to get it
2. **Single responsibility** - One agent = one LLM call
3. **Runtime agnostic** - Same spec works across different runners
4. **Output-focused** - Declare the schema, let the runtime extract it

## License

MIT License - see [LICENSE](LICENSE) for details.
