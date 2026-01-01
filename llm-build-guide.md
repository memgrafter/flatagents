# FlatAgents + FlatMachines Build Guide

## What They Are

**FlatAgent** (`flatagent.d.ts`): A single LLM call configured in YAML. Defines model, prompts, and output schema. No orchestration logic.

**FlatMachine** (`flatmachine.d.ts`): A state machine that orchestrates agents. Defines states, transitions, conditions, loops, and error handling. All orchestration is declarative.

## When to Use What

| Need | Solution |
|------|----------|
| Single LLM call | FlatAgent only |
| Multi-step workflow | FlatMachine + FlatAgents |
| Conditional branching | FlatMachine transitions |
| Retry with backoff | FlatMachine execution type |
| Error recovery | FlatMachine `on_error` |

## Python SDK

```bash
pip install flatagents[litellm]
```

```python
from flatagents import FlatAgent, FlatMachine

# Single agent call
agent = FlatAgent(config_file="agent.yml")
result = await agent.call(query="Hello")
print(result.output)

# State machine execution
machine = FlatMachine(config_file="machine.yml")
result = await machine.execute(input={"query": "Hello"})
print(result)
```

## Key Patterns

### Execution Types
Add to any state with an agent:
```yaml
execution:
  type: retry                    # retry | parallel | mdap_voting
  backoffs: [2, 8, 16, 35]       # Seconds between retries
  jitter: 0.1                    # ±10% random variation
```

### Error Handling
```yaml
on_error: error_state            # Transition on any error
# OR granular:
on_error:
  default: error_state
  RateLimitError: retry_state
```
Context receives: `last_error`, `last_error_type`

### Conditional Transitions
```yaml
transitions:
  - condition: "context.score >= 8"
    to: success
  - to: continue                   # Default fallback
```

### Loops
Self-reference creates loops (machine has `max_steps` safety):
```yaml
transitions:
  - condition: "context.done"
    to: finish
  - to: same_state
```

## Hooks (Code Extensibility)

When declarative config isn't enough, use Python hooks for imperative logic:

```python
from flatagents import FlatMachine, MachineHooks

class CustomHooks(MachineHooks):
    def on_state_enter(self, state: str, context: dict) -> dict:
        context["entered_at"] = time.time()
        return context
    
    def on_action(self, action: str, context: dict) -> dict:
        if action == "custom_logic":
            context["computed"] = expensive_calculation()
        return context

machine = FlatMachine(config_file="machine.yml", hooks=CustomHooks())
```

**Available hooks**: `on_state_enter`, `on_state_exit`, `on_action`, `on_transition`, `on_error`, `on_machine_start`, `on_machine_end`

Use hooks for: Pareto selection, population sampling, external API calls, database writes, complex validation.

## Feature Index

### Execution Types
| Type | Config | Use Case |
|------|--------|----------|
| `default` | (none) | Single agent call |
| `retry` | `backoffs: [2,8,16,35]`, `jitter: 0.1` | Rate limit handling |
| `parallel` | `n_samples: 5` | Multiple samples |
| `mdap_voting` | `k_margin: 3`, `max_candidates: 10` | Consensus voting |

### State Types
| Type | Behavior |
|------|----------|
| `initial` | Entry point (one per machine) |
| `final` | Exits machine, returns `output` |
| (none) | Normal state, must have transitions |

### State Fields
| Field | Purpose |
|-------|---------|
| `agent` | Agent to execute |
| `execution` | Execution type config |
| `on_error` | Error recovery state |
| `input` | Input mapping to agent |
| `output_to_context` | Map agent output to context |
| `transitions` | Where to go next |
| `action` | Hook action name |

### Transition Fields
| Field | Purpose |
|-------|---------|
| `condition` | Expression (e.g., `context.score >= 8`) |
| `to` | Target state name |

### Context Variables
| Variable | When Available |
|----------|----------------|
| `context.*` | All states |
| `input.*` | Initial context setup |
| `output.*` | In `output_to_context` after agent call |
| `context.last_error` | After error |
| `context.last_error_type` | After error |