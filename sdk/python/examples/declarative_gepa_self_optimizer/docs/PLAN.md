# Declarative GEPA Self-Optimizer Plan

## Overview

This project implements the GEPA (Genetic Prompt Algorithm) optimization algorithm using declarative agents. The implementation is **paper-compliant**, following Algorithm 1 (Main Loop) and Algorithm 2 (Pareto-Based Candidate Selection) from the GEPA paper.

Every LLM call is a declarative agent, making the entire system configurable via YAML files.

## Goal

Optimize a GEPA judge to better evaluate agent outputs. The judge determines whether an agent's response is correct, and we improve its accuracy through population-based prompt optimization with Pareto selection.

## GEPA Algorithm Overview

### Algorithm 1: Main Loop
```
Inputs: System Φ, dataset D_train, metric μ, feedback μ_f, budget B
Hyperparams: minibatch_size b, pareto_set_size n_pareto

1. Split D_train into D_feedback, D_pareto (|D_pareto| = n_pareto)
2. Initialize candidates P ← [Φ], parents A ← [None]
3. Evaluate base system on D_pareto → S[Φ]
4. While budget B not exhausted:
   a. k ← SelectCandidate(P, S)  # Pareto sampling
   b. j ← SelectModule(Φ_k)      # Round-robin (N/A for single module)
   c. M ← sample minibatch of size b from D_feedback
   d. Execute Φ_k on M, gather traces and feedback via μ_f
   e. π'_j ← ReflectiveUpdate(π_j, feedbacks, traces)
   f. Φ' ← copy Φ_k with module j updated to π'_j
   g. If score improved on M:
      - Add Φ' to P, record parent k in A
      - Evaluate Φ' on full D_pareto → S[Φ']
5. Return candidate maximizing average score on D_pareto
```

### Algorithm 2: Pareto-Based Candidate Selection
```
function SelectCandidate(P, S):
  # Find best candidates per instance
  for each instance i:
    s*[i] ← max_k S[P[k]][i]
    P*[i] ← {P[k] : S[P[k]][i] = s*[i]}

  # Collect Pareto frontier
  C ← unique candidates in ∪_i P*[i]

  # Remove dominated candidates
  Remove Φ from C if ∃Φ' in C that dominates Φ

  # Sample by frequency
  f[Φ] ← count of instances where Φ achieves best
  Sample Φ_k with probability ∝ f[Φ_k]
  return k
```

## Architecture

```
+-------------------------------------------------------------------------+
|                         GEPA Self-Optimizer                              |
+-------------------------------------------------------------------------+
|                                                                          |
|  +------------------------------------------------------------------+   |
|  |                        Data Splitting                             |   |
|  |  D_train ------+------------------+------------------------------ |   |
|  |                v                  v                               |   |
|  |           D_pareto           D_feedback         D_test            |   |
|  |          (scoring)         (minibatches)      (held-out)          |   |
|  +------------------------------------------------------------------+   |
|                                                                          |
|  +------------------------------------------------------------------+   |
|  |                     Population P                                  |   |
|  |  +--------+  +--------+  +--------+  +--------+                   |   |
|  |  |  Φ_0   |  |  Φ_1   |  |  Φ_2   |  |  Φ_3   |  ...              |   |
|  |  | (base) |  |        |  |        |  |        |                   |   |
|  |  +---+----+  +---+----+  +--------+  +--------+                   |   |
|  |      |           |                                                |   |
|  |      +-----+-----+  <- Ancestry Tree A                            |   |
|  |            v                                                      |   |
|  |   Per-instance scores S[Φ][i] on D_pareto                         |   |
|  +------------------------------------------------------------------+   |
|                           |                                              |
|                           v                                              |
|  +------------------------------------------------------------------+   |
|  |                    GEPA Iteration Loop                            |   |
|  |                                                                   |   |
|  |  1. SelectCandidate(P, S)     --> Pareto frontier sampling        |   |
|  |           |                                                       |   |
|  |           v                                                       |   |
|  |  2. Sample minibatch M        --> from D_feedback                 |   |
|  |           |                                                       |   |
|  |           v                                                       |   |
|  |  3. Execute Φ_k on M          --> Gather traces + feedback        |   |
|  |           |                                                       |   |
|  |           v                                                       |   |
|  |  4. ReflectiveUpdate          --> LLM proposes mutation           |   |
|  |     (reflective_updater.yml)       using traces                   |   |
|  |           |                                                       |   |
|  |           v                                                       |   |
|  |  5. Evaluate Φ' on M          --> Minibatch gating                |   |
|  |           |                                                       |   |
|  |           v                                                       |   |
|  |  6. If improved on M:                                             |   |
|  |     - Evaluate Φ' on D_pareto                                     |   |
|  |     - Add to P, record parent in A                                |   |
|  |                                                                   |   |
|  +------------------------------------------------------------------+   |
|                           |                                              |
|                           v                                              |
|  +------------------------------------------------------------------+   |
|  |                       Output                                      |   |
|  |  - Best Φ* = argmax avg score on D_pareto                         |   |
|  |  - Final eval on D_test                                           |   |
|  |  - Ancestry lineage of winning candidate                          |   |
|  +------------------------------------------------------------------+   |
+-------------------------------------------------------------------------+
```

## Declarative Agents

Every LLM call is defined as a declarative agent in `config/agents/`:

### 1. Judge Agent (`judge.yml`)
The target of optimization. Evaluates agent responses.

### 2. Task Generator Agent (`task_generator.yml`)
Generates diverse tasks for evaluation data.

### 3. Response Generator Agent (`response_generator.yml`)
Creates agent responses (both correct and flawed) for testing the judge.

### 4. Reflective Updater Agent (`reflective_updater.yml`)
**Core GEPA mutation mechanism.** Implements the paper's reflective meta-prompt:

```yaml
user: |
  I provided an assistant with the following instructions:
  '''
  {{ input.current_instruction }}
  '''

  Examples of task inputs, assistant responses, and feedback:
  '''
  {% for trace in input.traces %}
  Input: {{ trace.input | tojson }}
  Output: {{ trace.output | tojson }}
  Feedback: {{ trace.feedback }}
  ---
  {% endfor %}
  '''

  Your task: Write a new instruction for the assistant...
  1. Identify input format and detailed task description
  2. Extract all domain-specific factual information from feedback
  3. Include any generalizable strategies the assistant used
  4. Incorporate corrections for the failures shown in feedback
```

### 5. Summary Generator Agent (`summary_generator.yml`)
Generates optimization run summaries.

## File Structure

```
declarative_gepa_self_optimizer/
├── docs/
│   ├── PLAN.md                          # This file
│   ├── GEPA_COMPLIANCE_IMPROVEMENTS.md  # Analysis vs paper
│   └── gepa_paper.md                    # Paper algorithm reference
├── config/
│   ├── agents/
│   │   ├── judge.yml                    # Target judge agent
│   │   ├── task_generator.yml           # Generates evaluation tasks
│   │   ├── response_generator.yml       # Generates test responses
│   │   ├── reflective_updater.yml       # GEPA reflective mutation
│   │   └── summary_generator.yml        # Generates summaries
│   └── settings.yml                     # Optimizer settings
├── data/
│   ├── evaluation_set.json              # Generated evaluation data
│   └── .gitkeep
├── src/
│   ├── __init__.py
│   ├── data_generator.py                # Uses declarative agents to generate data
│   ├── evaluator.py                     # Runs judge and compares to ground truth
│   ├── optimizer.py                     # GEPA Algorithm 1 & 2 implementation
│   ├── prompt_evolver.py                # Reflective update via declarative agent
│   └── utils.py                         # Utilities
├── output/
│   ├── optimized_judge.yml              # Final optimized judge
│   └── optimization_log.json            # Optimization history
├── main.py                              # Entry point
└── requirements.txt
```

## Core Data Structures

### Candidate
```python
@dataclass
class Candidate:
    id: int
    config: dict                    # Judge configuration
    parent_id: Optional[int]        # Ancestry tracking (A)
    scores: dict[int, float]        # Per-instance scores on D_pareto
```

### Population
```python
@dataclass
class Population:
    candidates: list[Candidate]     # P: all candidates
    pareto_scores: dict[int, dict]  # S: scores per candidate per instance
```

### AncestryTree
```python
@dataclass
class AncestryTree:
    parents: dict[int, Optional[int]]  # A: candidate_id -> parent_id
```

## Configuration

```python
@dataclass
class OptimizationConfig:
    budget: int = 50              # B: Maximum mutation attempts
    pareto_set_size: int = 30     # n_pareto: |D_pareto|
    minibatch_size: int = 5       # b: |M| for minibatch evaluation
    test_split: float = 0.2       # Fraction held out for final test
    early_stop_patience: int = 10 # Stop if no new candidates for N iterations
```

## Usage

```bash
# Generate evaluation data
python main.py generate-data --num-examples 100

# Run GEPA optimization
python main.py run --budget 50 --pareto-size 30 --minibatch-size 5

# Evaluate a judge config
python main.py evaluate --judge config/agents/judge.yml

# Run optimization only (requires existing data)
python main.py optimize --budget 50
```

## Key Features

### Paper-Compliant Implementation

1. **Three-way data split**: D_feedback, D_pareto, D_test
2. **Pareto population**: Maintains all candidates, not just current best
3. **Pareto selection**: Algorithm 2 with dominance checking and frequency sampling
4. **Minibatch gating**: Only promotes candidates that improve on minibatch
5. **Ancestry tracking**: Records parent for each candidate
6. **Reflective meta-prompt**: Extracts factual knowledge from traces

### Declarative Agents

- Every prompt is visible and editable in YAML
- Easy to swap models or providers via litellm
- No hidden prompts in Python code
- Reproducible and version-controllable

## Metrics

### Primary Metrics

1. **Accuracy**: % of verdicts matching ground truth
2. **Balanced Accuracy**: Average of true positive and true negative rates
3. **Calibration Error**: Mean absolute difference between confidence and correctness

### Per-Instance Scoring

For Pareto selection, each candidate is scored on each D_pareto instance:
- Score = 1.0 if verdict matches ground truth
- Score = 0.0 otherwise

## Dependencies

- `declarativeagent`: For running declarative agents (from lib/microagent)
- `pyyaml`: Configuration files
- `jinja2`: Template rendering (via declarativeagent)
- `litellm`: LLM API calls (via declarativeagent)

## Success Criteria

1. Optimized judge achieves >90% accuracy on hold-out test set
2. Population maintains diversity (multiple candidates in Pareto frontier)
3. Best candidate has ancestry depth > 1 (accumulated learning)
4. Optimization completes within budget
