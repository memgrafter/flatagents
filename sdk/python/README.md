# FlatAgents Python SDK

Python SDK for [FlatAgents](https://github.com/memgrafter/flatagents)—YAML-configured AI agents and state machine orchestration.

LLM/machine readers: use MACHINES.md as a primary reference, it is more comprehensive and token efficient.

## Install

```bash
pip install flatagents[litellm]
```

## Quick Start

### Single Agent

**summarizer.yml**
```yaml
spec: flatagent
spec_version: "0.6.0"

data:
  name: summarizer
  model:
    provider: openai
    name: gpt-4o-mini
  system: You summarize text concisely.
  user: "Summarize: {{ input.text }}"
  output:
    summary:
      type: str
      description: A concise summary
```

```python
from flatagents import FlatAgent, setup_logging, get_logger

# Optional: Enable internal logging to see agent progress
setup_logging(level="INFO")
logger = get_logger(__name__)

agent = FlatAgent(config_file="summarizer.yml")
result = await agent.execute(input={"text": "Long article..."})

logger.info(f"Summary: {result['summary']}")
```

### State Machine

**machine.yml**
```yaml
spec: flatmachine
spec_version: "0.1.0"

data:
  name: writer-critic
  context:
    product: "{{ input.product }}"
    score: 0
  agents:
    writer: ./writer.yml
    critic: ./critic.yml
  states:
    start:
      type: initial
      transitions:
        - to: write
    write:
      agent: writer
      output_to_context:
        tagline: "{{ output.tagline }}"
      transitions:
        - to: review
    review:
      agent: critic
      output_to_context:
        score: "{{ output.score }}"
      transitions:
        - condition: "context.score >= 8"
          to: done
        - to: write
    done:
      type: final
      output:
        tagline: "{{ context.tagline }}"
```

```python
from flatagents import FlatMachine, setup_logging, get_logger

setup_logging(level="INFO")
logger = get_logger(__name__)

machine = FlatMachine(config_file="machine.yml")
result = await machine.execute(input={"product": "AI coding assistant"})

logger.info(f"Tagline: {result['tagline']}")
```

## Configuration

Both YAML and JSON configs are supported. Pass `config_file` for file-based configs or `config_dict` for inline configs.

## LLM Backends

```python
from flatagents import LiteLLMBackend, AISuiteBackend

# LiteLLM (default)
agent = FlatAgent(config_file="agent.yml")

# AISuite
backend = AISuiteBackend(model="openai:gpt-4o")
agent = FlatAgent(config_file="agent.yml", backend=backend)
```

## Hooks

Extend machine behavior with Python hooks:

```python
from flatagents import FlatMachine, MachineHooks

class CustomHooks(MachineHooks):
    def on_state_enter(self, state: str, context: dict) -> dict:
        context["entered_at"] = time.time()
        return context

    def on_action(self, action: str, context: dict) -> dict:
        if action == "fetch_data":
            context["data"] = fetch_from_api()
        return context

machine = FlatMachine(config_file="machine.yml", hooks=CustomHooks())
```

**Available hooks**: `on_machine_start`, `on_machine_end`, `on_state_enter`, `on_state_exit`, `on_transition`, `on_error`, `on_action`

**Built-in hooks**: `LoggingHooks`, `MetricsHooks`, `CompositeHooks`

## Execution Types

Configure how agents are executed in machine states:

```yaml
execution:
  type: retry              # retry | parallel | mdap_voting
  backoffs: [2, 8, 16, 35] # Seconds between retries
  jitter: 0.1              # ±10% random variation
```

| Type | Use Case |
|------|----------|
| `default` | Single call |
| `retry` | Rate limit handling with backoff |
| `parallel` | Multiple samples (`n_samples`) |
| `mdap_voting` | Consensus voting (`k_margin`, `max_candidates`) |

## Schema Validation

```python
from flatagents import validate_flatagent_config, validate_flatmachine_config

# Returns list of warnings/errors
warnings = validate_flatagent_config(config)
warnings = validate_flatmachine_config(config)
```

## Examples

- **[helloworld](examples/helloworld)** — Minimal getting started
- **[writer_critic](examples/writer_critic)** — Iterative refinement loop
- **[mdap](examples/mdap)** — Multi-step reasoning with calibrated confidence
- **[error_handling](examples/error_handling)** — Error recovery patterns

## Logging & Metrics

FlatAgents provides built-in standardized logging and OpenTelemetry-based metrics.

### Logging

```python
from flatagents import setup_logging, get_logger

# Configure once (respects FLATAGENTS_LOG_LEVEL env var)
setup_logging(level="INFO")
logger = get_logger(__name__)

logger.info("Agent starting...")
```

**Environment Variables:**
- `FLATAGENTS_LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- `FLATAGENTS_LOG_FORMAT`: `standard`, `json`, `simple`

### Metrics (OpenTelemetry)

Track performance, token usage, and costs. Metrics are opt-in.

```bash
pip install flatagents[metrics]
export FLATAGENTS_METRICS_ENABLED=true
```

```python
from flatagents import AgentMonitor

with AgentMonitor("my-agent") as monitor:
    result = await agent.execute(input)
    # Automatically tracks duration, status, and can record custom metrics
    monitor.metrics["tokens"] = 1200
```

Supported backends via OTLP: Datadog, Honeycomb, StatsD (via collector), etc.

## Specs

See [`flatagent.d.ts`](../../flatagent.d.ts) and [`flatmachine.d.ts`](../../flatmachine.d.ts) for full specifications.

See [MACHINES.md](MACHINES.md) for state machine patterns and reference.

## License

MIT — see [LICENSE](../../LICENSE)
