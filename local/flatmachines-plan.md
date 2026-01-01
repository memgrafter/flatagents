# Flatmachines: State Machine Configuration for Flatagents

## Summary

Flatmachines aims to extract orchestration logic from Python code into declarative configurations, complementing flatagents. While flatagents defines **what** each agent is (model + prompts + output schema), flatmachines defines **how** agents are connected and executed (states, transitions, conditions, loops).

---

## Current State Analysis

### What We Found in the Examples

After reviewing all 6 examples in the SDK, I identified distinct orchestration patterns that are currently implemented in Python code:

| Example | Pattern | Orchestration Logic Location |
|---------|---------|------------------------------|
| **helloworld** | Simple loop until condition | `main.py` lines 38-52 |
| **writer_critic** | Multi-agent feedback loop | `main.py` lines 68-97 |
| **search_refiner** | Sequential pipeline with MCP tools | `main.py` lines 111-181 |
| **mdap** | Voting/sampling with state updates | `mdap.py`, `demo.py` |
| **gepa_self_optimizer** | Genetic algorithm with population management | `optimizer.py` (780 lines) |
| **mcp_exa** | Tool orchestration | Similar to search_refiner |

### Orchestration Logic That Needs Extraction

1. **Loops with termination conditions**
   - `while current != target` (helloworld)
   - `while score < target_score and round < max_rounds` (writer_critic)
   - `while not solved and step < max_steps` (mdap)

2. **Agent chaining/pipelines**
   - search → refine (search_refiner)
   - writer → critic → writer (writer_critic)

3. **Data flow between agents**
   - Output of one agent becomes input to another
   - State accumulation across iterations

4. **Conditional branching**
   - If score >= threshold, stop
   - If no tool calls, done
   - If improvement, promote candidate

5. **Parallel execution** (future)
   - MDAP's multi-sampling
   - Batch evaluations

---

## CEL Expression Language Evaluation

### Pros of CEL (Common Expression Language)
- Designed for configuration files (originated at Google for Kubernetes/IAM)
- Safe sandboxed execution (no side effects)
- Type-safe with static analysis
- JSON-friendly syntax
- Cross-platform (cel-go, cel-python, cel-java)

### Concerns
- **cel-go as 10-15MB WASM bundle**: This is for browser/edge use. For Python SDK, we'd use [cel-python](https://github.com/cloud-custodian/cel-python) which is pure Python
- **Long-term JSON support**: CEL expressions are just strings in JSON/YAML - no special encoding needed

### Why Add CEL Later (Not Now)

#### 1. Simple Syntax Covers 90%+ of Real Use Cases

Looking at the actual conditions in the 6 examples:

| Example | Conditions Used | Simple Syntax? |
|---------|----------------|----------------|
| helloworld | `current == target` | ✅ Yes |
| writer_critic | `score >= 8`, `round >= 4` | ✅ Yes |
| mdap | `pegs == goal`, `step >= max_steps` | ✅ Yes |
| search_refiner | `tool_calls is empty` | ✅ Yes |
| gepa_self_optimizer | Complex (Pareto, populations) | ❌ Needs hooks |

**Every real condition in the examples** falls into one of these patterns:
```
# Equality
context.current == context.target

# Comparison
context.score >= 8

# Boolean
context.solved == true

# Compound
context.score >= 8 or context.round >= 4
```

A simple expression parser handles these trivially. CEL's power (list comprehensions, macros, nested field access) isn't needed.

#### 2. CEL Adds Friction to Adoption

| Factor | Simple Syntax | CEL |
|--------|---------------|-----|
| Dependencies | 0 new | cel-python + protobuf |
| Learning curve | None (intuitive) | ~30 min for basics |
| Error messages | Clear, custom | CEL parser errors |
| Debugging | Simple eval trace | CEL runtime trace |
| TypeScript parity | Easy to implement | Need cel-js or WASM |

For a v0.1.0 prototype, removing adoption friction is critical.

#### 3. Clean Migration Path Exists

The key insight: **CEL is a superset of simple expressions**. Any expression that works in our simple parser will work identically in CEL.

```yaml
# v0.1.0 - Simple parser
condition: "context.score >= 8"

# v0.2.0 - CEL enabled (same syntax works!)
condition: "context.score >= 8"

# v0.2.0 - Now CEL features available for power users
condition: "context.scores.all(s, s >= 5)"  # CEL list macro
```

**No breaking changes, no migration required.** Users who need CEL can enable it; others don't notice.

#### 4. Hooks Already Handle the Complex Cases

The only example that needs complex logic (GEPA) cannot be expressed in CEL anyway:
- Pareto-optimal selection across candidates
- Population sampling with weighted probabilities
- Ancestry tree traversal

These require **imperative code**, not expressions. Hooks solve this cleanly:

```python
class GEPAHooks(MachineHooks):
    def select_candidate(self, context: dict) -> int:
        # 50 lines of Python for Pareto selection
        # CEL can't do this - it has no side effects
        return best_candidate_id
```

#### 5. Risk Analysis

| Risk | Adding CEL Now | Adding CEL Later |
|------|---------------|------------------|
| Scope creep | High - tempted to use CEL everywhere | Low - defined boundary |
| Ship delay | +1-2 weeks for CEL integration | None |
| TypeScript SDK | Blocked on cel-js/WASM decision | Independent |
| User confusion | "When do I use CEL vs hooks?" | Clear: simple syntax for transitions, hooks for logic |
| Wrong abstraction | Locked into CEL's model | Can evaluate alternatives |

#### 6. When to Add CEL (Phase 3)

Add CEL when users demonstrate these needs:
- List/map operations in conditions (`context.scores.filter(s, s > 5).size() >= 3`)
- String manipulation (`context.name.startsWith("test_")`)
- Timestamp/duration comparisons (`context.created_at > now - duration("24h")`)

At that point, CEL provides clear value over hooks.

### Recommendation: Dual-Mode Expression Engine (v0.1.0)

Ship both modes in v0.1.0, with simple mode as the default:

```yaml
spec: flatmachine
spec_version: "0.1.0"

data:
  name: my-workflow
  
  # Expression engine selection
  expression_engine: simple  # default - or "cel"
  
  states:
    check:
      transitions:
        - condition: "context.score >= 8"
          to: done
```

#### Mode Comparison

| Aspect | Simple Mode | CEL Mode |
|--------|-------------|----------|
| **Default** | ✅ Yes | No |
| **Dependencies** | None | `pip install flatagents[cel]` |
| **Install** | `pip install flatagents` | `pip install flatagents[cel]` |
| **Basic syntax** | `context.score >= 8` | `context.score >= 8` (identical!) |
| **Compound** | `a >= 8 and b < 10` | `a >= 8 && b < 10` |
| **List operations** | ❌ Use hooks | `scores.all(s, s >= 5)` |
| **String methods** | ❌ Use hooks | `name.startsWith("test_")` |
| **Timestamps** | ❌ Use hooks | `created > now - duration("1h")` |

#### Simple Mode Syntax (Built-in)

```
# Comparisons
context.score >= 8
context.current == context.target
output.status != "error"

# Boolean operators
context.score >= 8 and context.round < 4
context.solved or context.timeout
not context.failed

# Field access
context.nested.field.value
input.user.name
output.result

# Literals
context.name == "test"
context.count == 42
context.enabled == true
context.data == null
```

#### CEL Mode Syntax (Optional Extra)

All simple mode syntax works, plus:

```
# List macros
context.scores.all(s, s >= 5)
context.items.exists(i, i.status == "active")
context.values.filter(v, v > 0).size() >= 3

# String methods  
context.name.startsWith("test_")
context.email.contains("@")
context.path.endsWith(".json")

# Timestamps and durations
context.created_at > now - duration("24h")
context.expires_at < timestamp("2025-01-01T00:00:00Z")

# Type coercion
int(context.score_str) >= 8
string(context.count) + " items"
```

#### Why This Approach Works

1. **Zero friction for most users** - Simple mode has no dependencies, covers 90%+ of cases
2. **Power users get CEL immediately** - No waiting for Phase 3
3. **Same basic syntax** - `context.score >= 8` works in both modes
4. **Clear upgrade path** - Just add `[cel]` extra and set `expression_engine: cel`
5. **TypeScript SDK flexibility** - Implement simple mode first, add CEL via WASM later
6. **Graceful errors** - If user tries CEL syntax in simple mode, error says "install flatagents[cel]"

#### Implementation

```python
# In flatagents/expressions/__init__.py

def get_expression_engine(mode: str = "simple"):
    if mode == "simple":
        from .simple import SimpleExpressionEngine
        return SimpleExpressionEngine()
    elif mode == "cel":
        try:
            from .cel import CELExpressionEngine
            return CELExpressionEngine()
        except ImportError:
            raise ImportError(
                "CEL expression engine requires: pip install flatagents[cel]"
            )
    else:
        raise ValueError(f"Unknown expression engine: {mode}")
```

---

## Proposed Flatmachine Schema

### Core Concepts

1. **Machine** - A state machine configuration (like a flatagent config)
2. **State** - A named state that executes an agent or action
3. **Transition** - Condition-based movement between states
4. **Context** - Data that flows through the machine (accumulated state)

### Schema Design (v0.1.0)

```yaml
spec: flatmachine
spec_version: "0.1.0"

data:
  name: writer-critic-loop
  
  # Initial context values
  context:
    product: "{{ input.product }}"
    tagline: null
    feedback: null
    score: 0
    round: 0
  
  # Agent references - can be inline or file paths
  agents:
    writer: ./writer.yml
    critic: ./critic.yml
  
  # State machine definition
  states:
    start:
      type: initial
      transitions:
        - to: write
    
    write:
      agent: writer
      execution:
        type: retry
        backoffs: [2, 8, 16, 35]  # Delay array in seconds
        jitter: 0.1  # 10% random variation
      on_error: error_state  # Declarative error handling
      input:
        product: "{{ context.product }}"
        tagline: "{{ context.tagline }}"
        feedback: "{{ context.feedback }}"
      output_to_context:
        tagline: "{{ output.tagline }}"
      transitions:
        - to: review
    
    review:
      agent: critic
      execution:
        type: retry
      on_error:  # Granular error routing
        default: error_state
        RateLimitError: write  # Retry from writer
      input:
        product: "{{ context.product }}"
        tagline: "{{ context.tagline }}"
      output_to_context:
        score: "{{ output.score }}"
        feedback: "{{ output.feedback }}"
        round: "{{ context.round + 1 }}"
      transitions:
        - condition: "context.score >= 8"
          to: done
        - condition: "context.round >= 4"
          to: done
        - to: write  # default
    
    error_state:
      type: final
      output:
        error: true
        message: "{{ context.last_error }}"
    
    done:
      type: final
      output:
        tagline: "{{ context.tagline }}"
        score: "{{ context.score }}"
        rounds: "{{ context.round }}"

metadata:
  description: "Writer-critic feedback loop"
```

### Key Design Decisions

1. **Agents remain unchanged** - Flatagents configs are referenced, not modified
2. **Context is the state** - All data flows through a mutable context object
3. **Transitions are ordered** - First matching condition wins (like if-elif-else)
4. **Jinja2 for data mapping** - Same templating as flatagents for consistency
5. **Simple expression syntax** - Comparisons and boolean logic only (initially)
6. **Execution types** - Customize agent call behavior (retry, parallel, voting)
7. **Declarative error handling** - `on_error` routes failures to recovery states

---

## Hooks System

The hooks system allows extending machine behavior without modifying core logic:

```python
from flatagents import FlatMachine, MachineHooks

class WriterCriticHooks(MachineHooks):
    """Custom hooks for the writer-critic workflow."""
    
    def on_state_enter(self, state_name: str, context: dict) -> dict:
        """Called before executing a state. Can modify context."""
        if state_name == "write":
            # Custom pre-processing
            context["attempt_time"] = datetime.now().isoformat()
        return context
    
    def on_state_exit(self, state_name: str, context: dict, output: dict) -> dict:
        """Called after executing a state. Can modify output."""
        return output
    
    def on_transition(self, from_state: str, to_state: str, context: dict) -> str:
        """Can override transition target. Return state name."""
        if to_state == "done" and context.get("force_continue"):
            return "write"  # Override the transition
        return to_state
    
    def on_error(self, state_name: str, error: Exception, context: dict) -> str:
        """Handle execution errors. Return next state or raise."""
        logger.error(f"Error in {state_name}: {error}")
        return "error_state"

# Usage
machine = FlatMachine(config_file="writer_critic.yml", hooks=WriterCriticHooks())
result = await machine.execute(input={"product": "AI CLI tool"})
```

### Default Hooks (Base Implementation)

The SDK provides default hook implementations:
- **Logging hooks** - Log all state transitions
- **Retry hooks** - Retry failed agent calls
- **Timeout hooks** - Enforce execution time limits
- **Metrics hooks** - Track execution statistics

---

## Examples to Dry Out

Here's how each example would be converted:

### 1. HelloWorld → Simple Loop Machine

```yaml
spec: flatmachine
spec_version: "0.1.0"

data:
  name: hello-world-loop
  
  context:
    target: "{{ input.target }}"
    current: ""
  
  agents:
    builder: ./agent.yml
  
  states:
    start:
      type: initial
      transitions:
        - condition: "context.current == context.target"
          to: done
        - to: build_char
    
    build_char:
      agent: builder
      input:
        current: "{{ context.current }}"
        target: "{{ context.target }}"
      output_to_context:
        current: "{{ context.current + output.next_char }}"
      transitions:
        - condition: "context.current == context.target"
          to: done
        - to: build_char
    
    done:
      type: final
      output:
        result: "{{ context.current }}"
```

### 2. Writer-Critic → Feedback Loop Machine
(Shown in schema design above)

### 3. Search-Refiner → Sequential Pipeline

```yaml
spec: flatmachine
spec_version: "0.1.0"

data:
  name: search-refine-pipeline
  
  context:
    query: "{{ input.query }}"
    search_results: null
    refined_results: null
  
  agents:
    searcher: ./search.yml
    refiner: ./refiner.yml
  
  states:
    start:
      type: initial
      transitions:
        - to: search
    
    search:
      agent: searcher
      tool_loop: true  # Enable MCP tool orchestration
      input:
        query: "{{ context.query }}"
      output_to_context:
        search_results: "{{ output.content }}"
      transitions:
        - to: refine
    
    refine:
      agent: refiner
      input:
        query: "{{ context.query }}"
        search_results: "{{ context.search_results }}"
      output_to_context:
        refined_results: "{{ output.content }}"
      transitions:
        - to: done
    
    done:
      type: final
      output:
        results: "{{ context.refined_results }}"
```

### 4. MDAP → Voting Machine (More Complex)

MDAP requires hooks for the voting logic:

```yaml
spec: flatmachine
spec_version: "0.1.0"

data:
  name: mdap-hanoi
  
  context:
    pegs: "{{ input.initial_pegs }}"
    goal: "{{ input.goal_pegs }}"
    previous_move: null
    step: 0
  
  agents:
    solver: ./hanoi.yml
  
  settings:
    hooks: mdap.voting_hooks  # Python module with voting logic
    sampling:
      max_candidates: 10
      k_margin: 3
  
  states:
    start:
      type: initial
      transitions:
        - condition: "context.pegs == context.goal"
          to: done
        - to: solve_step
    
    solve_step:
      agent: solver
      sampling: multi  # Triggers voting hook
      input:
        pegs: "{{ context.pegs }}"
        previous_move: "{{ context.previous_move }}"
      output_to_context:
        pegs: "{{ output.predicted_state }}"
        previous_move: "{{ output.move }}"
        step: "{{ context.step + 1 }}"
      transitions:
        - condition: "context.pegs == context.goal"
          to: done
        - condition: "context.step >= 20"
          to: failed
        - to: solve_step
    
    done:
      type: final
      output:
        solved: true
        steps: "{{ context.step }}"
    
    failed:
      type: final
      output:
        solved: false
        steps: "{{ context.step }}"
```

### 5. GEPA Self-Optimizer → Complex Algorithm Machine

GEPA is the most complex - it would need significant hook implementation:

```yaml
spec: flatmachine
spec_version: "0.1.0"

data:
  name: gepa-optimizer
  
  settings:
    hooks: gepa.optimizer_hooks
  
  states:
    start:
      type: initial
      action: initialize_population  # Hook action
      transitions:
        - to: iterate
    
    iterate:
      action: select_candidate  # Hook action (Pareto selection)
      transitions:
        - condition: "context.budget_exhausted"
          to: finalize
        - to: mutate
    
    mutate:
      action: reflective_update  # Uses reflective_updater agent
      transitions:
        - condition: "context.child_improved"
          to: promote
        - to: iterate
    
    promote:
      action: add_to_population
      transitions:
        - to: iterate
    
    finalize:
      type: final
      action: save_best_candidate
```

> **Note:** GEPA requires extensive hooks - The algorithm is too complex for pure declarative config. The flatmachine would orchestrate the high-level flow, while hooks implement:
> - Population management
> - Pareto-based selection
> - Minibatch sampling
> - Fitness evaluation

---

## Implementation Roadmap

### Phase 1: Core Engine (MVP)
- [x] `FlatMachine` class with state execution
- [x] Simple expression parser (comparisons, boolean)
- [x] CEL expression engine (optional extra)
- [x] Context management
- [x] Agent integration
- [x] Basic hooks interface

### Phase 2: Standard Patterns & Execution Types
- [x] Loop detection and execution (via self-referential transitions + max_steps)
- [x] Sequential pipelines (state → state → state flows)
- [x] Conditional branching (transition conditions with expressions)
- [x] Error state handling (on_error: simple string or error-type dict)
- [x] **Execution types** - declarative agent call modifiers

#### Execution Types

Execution types allow customizing **how** an agent is called, declared in YAML rather than requiring manual Python hook wiring. This keeps the machine configuration fully declarative ("flat").

**Schema:**
```yaml
states:
  solve_step:
    agent: solver
    execution:
      type: mdap_voting  # Execution type name
      k_margin: 3        # Type-specific config
      max_candidates: 10
    input:
      pegs: "{{ context.pegs }}"
```

**Built-in Execution Types:**

| Type | Description | Config |
|------|-------------|--------|
| `default` | Standard single agent call | (none) |
| `mdap_voting` | Multi-sample with first-to-ahead-by-k voting | `k_margin`, `max_candidates` |
| `parallel` | Run N samples in parallel, return all | `n_samples` |
| `retry` | Retry on failure with configurable backoffs | `backoffs`, `jitter` |

**MDAP Voting Example:**

The MDAP voting execution type implements the first-to-ahead-by-k algorithm from the MAKER paper:
1. Sample the agent multiple times
2. Parse each response using the agent's `metadata.parsing` patterns
3. Validate against `metadata.validation` schema
4. Red-flag invalid responses
5. Vote with k-margin stopping rule
6. Return winning response

This replaces the manual Python loop in `demo_machine.py` - the entire orchestration is driven by `machine.yml`:

```python
# Before: Manual loop with hook wiring
mdap_hooks = MDAPHooks()
while context['step'] < 20:
    result = await mdap_hooks.voting_call(agent, input_data)
    # ... update context ...

# After: Pure YAML-driven execution
machine = FlatMachine(config_file="machine.yml")
result = await machine.execute(input={...})
```

**Key Principle:** Execution types are orchestration behavior (not agents) because they don't have their own LLM call. They modify how an existing agent is called. The config is in YAML; the implementation is internal to FlatMachine.

### Phase 3: Advanced Features
- [ ] Parallel state execution
- [ ] Tool loop integration (MCP)
- [ ] Custom execution type plugins

### Phase 4: Ecosystem
- [ ] Visual machine editor
- [ ] Machine validation/linting
- [ ] TypeScript SDK parity
- [ ] Machine testing framework
