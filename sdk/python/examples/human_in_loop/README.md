# Human-in-the-Loop Example

A simple example demonstrating human-in-the-loop workflows with flatmachines.

## Overview

This example shows how to:
1. Pause machine execution for human input
2. Incorporate human feedback into agent revisions
3. Allow humans to approve or request changes

## Flow

```
┌─────────────────┐
│      start      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  generate_draft │◄──────────┐
└────────┬────────┘           │
         │                    │
         ▼                    │ feedback
┌─────────────────┐           │
│ await_human_    │───────────┘
│    review       │
└────────┬────────┘
         │ approved
         ▼
┌─────────────────┐
│      done       │
└─────────────────┘
```

## Usage

```bash
cd sdk/python/examples/human_in_loop

# Run with a topic
python -m src.main "Benefits of remote work"

# With custom max revisions
python -m src.main "AI in healthcare" --max-revisions 5
```

## Key Concepts

### Hook Actions

The `await_human_review` state uses a hook action:

```yaml
await_human_review:
  action: human_review  # Triggers HumanInLoopHooks.on_action()
  transitions:
    - condition: "context.human_approved == true"
      to: done
```

### The Hook

```python
class HumanInLoopHooks(MachineHooks):
    def on_action(self, action_name: str, context: Dict) -> Dict:
        if action_name == "human_review":
            # Show draft, get input, update context
            context["human_approved"] = True/False
            context["human_feedback"] = "..."
        return context
```

## Extending This Example

- **Web UI**: Replace terminal input with a web endpoint
- **Async Approval**: Store pending reviews in a database
- **Multi-Approver**: Require multiple humans to approve
- **Timeout**: Auto-approve after N minutes
