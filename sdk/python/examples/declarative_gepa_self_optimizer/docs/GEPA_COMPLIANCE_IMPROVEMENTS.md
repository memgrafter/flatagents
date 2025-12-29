# GEPA Compliance Improvements

This document details the changes required to make the declarative GEPA implementation compliant with the paper's algorithm.

## Executive Summary

The current implementation is **GEPA-inspired** rather than **GEPA-compliant**. It implements a valid prompt optimization loop, but the core algorithmic innovations from the paper—**Pareto illumination** for diversity preservation and **population-based evolution**—are missing.

The current implementation is a **greedy hill-climbing optimizer** rather than the paper's **population-based Pareto search**.

---

## Discrepancy Analysis

### 1. Data Split Strategy

| Paper | Current Implementation |
|-------|------------------------|
| Splits D_train into **D_feedback** + **D_pareto** | Uses **train/test split** only |
| D_pareto used for candidate scoring (step 4g) | No separate pareto evaluation set |
| D_feedback used for minibatch sampling (step 4c) | Full train set used for all evaluation |

**Impact**: Paper uses D_pareto as a held-out set *within training* to validate candidates before promotion. Current implementation evaluates on full train set.

### 2. Pareto-Based Candidate Selection (Algorithm 2)

| Paper | Current Implementation |
|-------|------------------------|
| Maintains **population P** of all candidates | Single candidate chain |
| **Per-instance best tracking**: finds which candidate is best on each example | Aggregate accuracy comparison |
| **Pareto frontier**: keeps candidates that are best on *any* instance | No diversity preservation |
| **Frequency-weighted sampling**: samples from frontier proportional to "wins" | LLM-based `candidate_ranker` selects best |

**Impact**: Paper's Pareto illumination **maintains diversity** - a candidate that's best on even one example survives. Current implementation always picks the global best, which can collapse diversity and get stuck in local optima.

### 3. Module Selection (Round-Robin)

| Paper | Current Implementation |
|-------|------------------------|
| System has **multiple modules** (prompts) | **Single module** (judge prompt) |
| **Round-robin selection** across modules (step 4b) | N/A - only one target |

**Impact**: Not a discrepancy if intentionally single-module. Paper's approach is for multi-prompt pipelines.

### 4. Minibatch-First Evaluation

| Paper | Current Implementation |
|-------|------------------------|
| **Step 4d**: Execute on minibatch M first | Evaluate candidates on full train set |
| **Step 4g**: Only evaluate on full D_pareto if improved on M | No minibatch gating |

**Impact**: Paper is more compute-efficient - bad candidates are filtered early on cheap minibatch evaluation. Current implementation may waste LLM calls evaluating obviously bad candidates on full dataset.

### 5. Reflective Update Meta-Prompt

**Paper's exact structure** (from gepa_paper.md):
```
I provided an assistant with the following instructions:
'''
{current_instruction}
'''

Examples of task inputs, assistant responses, and feedback:
'''
{inputs_outputs_feedbacks}
'''

Your task: Write a new instruction...
- Identify input format and detailed task description
- Extract all domain-specific factual information from feedback
- Include any generalizable strategies...
```

**Current `prompt_proposer.yml`**: Different structure - uses failure patterns, suggested fixes, and prompt engineering principles. Missing:
- Explicit instruction to extract "domain-specific factual information from feedback"
- The specific "generalizable strategies" extraction
- The `inputs_outputs_feedbacks` trace format

**Impact**: Paper emphasizes extracting **factual knowledge** from traces into prompts. Current proposer focuses on failure patterns rather than mining traces for facts.

### 6. Population & Ancestry Tracking

| Paper | Current Implementation |
|-------|------------------------|
| `P <- [Phi]` - maintains all candidates ever created | Keeps only current best |
| `A <- [None]` - tracks parent ancestry | No ancestry tracking |
| Candidates accumulate improvements across genetic tree | Each iteration starts fresh from current best |

**Impact**: Paper builds a **genetic tree** where learnings accumulate. Current implementation is a **greedy hill-climb** - each iteration improves on current best without remembering alternatives.

---

## Severity Assessment

| Issue | Severity | Reason |
|-------|----------|--------|
| No Pareto population | **High** | Loses diversity, may converge to local optima |
| No minibatch gating | **Medium** | Compute inefficiency, not correctness issue |
| Different data split | **Medium** | May overfit to train set |
| Different meta-prompt | **Medium** | May miss factual knowledge extraction |
| No ancestry tracking | **Low** | Mainly affects interpretability |

---

## Required Changes

### 1. Data Split: D_feedback + D_pareto

**Current** (`optimizer.py:161-164`):
```python
def split_data(self, examples: list[dict]) -> tuple[list[dict], list[dict]]:
    split_idx = int(len(examples) * self.config.train_test_split)
    return examples[:split_idx], examples[split_idx:]  # train, test
```

**Required**: Three-way split matching paper's Algorithm 1, step 1:

```python
def split_data(self, examples: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Split into D_feedback, D_pareto, and D_test.

    - D_feedback: Used for minibatch sampling during mutation (large)
    - D_pareto: Used for candidate scoring/selection (small, fixed)
    - D_test: Held out for final evaluation
    """
    n = len(examples)
    # Paper uses n_pareto as hyperparameter (typically small, e.g., 20-50)
    n_pareto = self.config.pareto_set_size  # Add to OptimizationConfig
    n_test = int(n * 0.2)  # 20% for final test

    d_test = examples[:n_test]
    d_pareto = examples[n_test:n_test + n_pareto]
    d_feedback = examples[n_test + n_pareto:]

    return d_feedback, d_pareto, d_test
```

**Config addition**:
```python
@dataclass
class OptimizationConfig:
    # ... existing fields ...
    pareto_set_size: int = 30  # |D_pareto| - paper recommends 20-50
    minibatch_size: int = 5    # |M| for minibatch evaluation
```

---

### 2. Pareto Population & Selection Algorithm

This is the **core algorithmic change**. New data structures and the SelectCandidate algorithm are required.

**New data structures** (add to `optimizer.py`):

```python
@dataclass
class Candidate:
    """A candidate system configuration."""
    id: int
    config: dict
    parent_id: Optional[int]  # For ancestry tracking
    scores: dict[int, float]  # instance_idx -> score on D_pareto

@dataclass
class Population:
    """Population of candidates with per-instance scores."""
    candidates: list[Candidate]
    pareto_scores: dict[int, dict[int, float]]  # candidate_id -> {instance_idx -> score}

    def add_candidate(self, candidate: Candidate, scores: dict[int, float]):
        self.candidates.append(candidate)
        self.pareto_scores[candidate.id] = scores
```

**SelectCandidate algorithm** (paper's Algorithm 2):

```python
def select_candidate(self, population: Population, d_pareto: list[dict]) -> int:
    """
    Pareto-based candidate selection.

    Returns index of selected candidate for mutation.
    """
    n_instances = len(d_pareto)
    n_candidates = len(population.candidates)

    # Step 1: Find best candidates per instance
    best_per_instance: dict[int, list[int]] = {}  # instance -> [candidate_ids with best score]

    for i in range(n_instances):
        best_score = -float('inf')
        best_candidates = []

        for candidate in population.candidates:
            score = population.pareto_scores[candidate.id].get(i, 0)
            if score > best_score:
                best_score = score
                best_candidates = [candidate.id]
            elif score == best_score:
                best_candidates.append(candidate.id)

        best_per_instance[i] = best_candidates

    # Step 2: Collect Pareto frontier (candidates that are best on at least one instance)
    frontier_ids = set()
    for instance_bests in best_per_instance.values():
        frontier_ids.update(instance_bests)

    # Step 3: Remove dominated candidates
    # Candidate A dominates B if A >= B on all instances and A > B on at least one
    non_dominated = set(frontier_ids)
    for a_id in frontier_ids:
        for b_id in frontier_ids:
            if a_id == b_id:
                continue
            if self._dominates(population, a_id, b_id, n_instances):
                non_dominated.discard(b_id)

    # Step 4: Sample by frequency (count of instances where candidate achieves best)
    frequency: dict[int, int] = {cid: 0 for cid in non_dominated}
    for instance_bests in best_per_instance.values():
        for cid in instance_bests:
            if cid in frequency:
                frequency[cid] += 1

    # Weighted random sample
    candidates = list(frequency.keys())
    weights = [frequency[cid] for cid in candidates]
    total = sum(weights)
    weights = [w / total for w in weights]

    import random
    selected_id = random.choices(candidates, weights=weights, k=1)[0]

    return selected_id

def _dominates(self, pop: Population, a_id: int, b_id: int, n_instances: int) -> bool:
    """Check if candidate A dominates candidate B."""
    dominated = True
    strictly_better = False

    for i in range(n_instances):
        a_score = pop.pareto_scores[a_id].get(i, 0)
        b_score = pop.pareto_scores[b_id].get(i, 0)

        if a_score < b_score:
            dominated = False
            break
        if a_score > b_score:
            strictly_better = True

    return dominated and strictly_better
```

**Note**: The LLM-based `candidate_ranker` agent becomes unnecessary—Pareto selection is algorithmic.

---

### 3. Minibatch Gating Strategy

**Current flow** (`optimizer.py:231-251`): Evaluates every candidate on full train set.

**Paper's flow** (Algorithm 1, steps 4c-4g):
1. Sample minibatch M from D_feedback
2. Execute candidate on M, get score
3. **Only if improved on M**: promote to full D_pareto evaluation

**New iteration structure**:

```python
async def run_iteration(
    self,
    iteration: int,
    population: Population,
    d_feedback: list[dict],
    d_pareto: list[dict],
) -> Optional[Candidate]:
    """
    Single GEPA iteration with minibatch gating.

    Returns new candidate if one was created and promoted, else None.
    """
    # Step 4a: Select candidate from population via Pareto sampling
    parent_id = self.select_candidate(population, d_pareto)
    parent = next(c for c in population.candidates if c.id == parent_id)

    # Step 4c: Sample minibatch from D_feedback
    import random
    minibatch = random.sample(d_feedback, min(self.config.minibatch_size, len(d_feedback)))

    # Step 4d: Execute parent on minibatch, gather traces and feedback
    evaluator = JudgeEvaluator(judge_config_dict=parent.config)
    parent_minibatch_result = await evaluator.evaluate_dataset(minibatch, show_progress=False)
    parent_minibatch_score = parent_minibatch_result.accuracy

    # Step 4e: Reflective update - propose mutation based on failures
    if not parent_minibatch_result.failures:
        logger.info("No failures on minibatch, skipping mutation")
        return None

    # Gather traces (inputs, outputs, feedback) for reflective update
    traces = self._gather_traces(minibatch, parent_minibatch_result)

    candidate_prompt = await self.prompt_evolver.reflective_update(
        current_prompts=parent.config,
        traces=traces,
    )

    # Step 4f: Create child candidate
    child_config = self.prompt_evolver.create_candidate_config(parent.config, candidate_prompt)

    # Evaluate child on SAME minibatch
    child_evaluator = JudgeEvaluator(judge_config_dict=child_config)
    child_minibatch_result = await child_evaluator.evaluate_dataset(minibatch, show_progress=False)
    child_minibatch_score = child_minibatch_result.accuracy

    # Step 4g: Only promote if improved on minibatch
    if child_minibatch_score <= parent_minibatch_score:
        logger.info(f"Child ({child_minibatch_score:.1f}%) did not improve on parent ({parent_minibatch_score:.1f}%) on minibatch")
        return None

    logger.info(f"Child improved: {parent_minibatch_score:.1f}% -> {child_minibatch_score:.1f}% on minibatch")

    # Promote: Evaluate on full D_pareto
    child_pareto_scores = await self._evaluate_on_pareto(child_config, d_pareto)

    child = Candidate(
        id=len(population.candidates),
        config=child_config,
        parent_id=parent_id,
        scores=child_pareto_scores,
    )

    population.add_candidate(child, child_pareto_scores)

    return child

def _gather_traces(self, examples: list[dict], result: EvaluationResult) -> list[dict]:
    """Gather (input, output, feedback) traces for reflective update."""
    traces = []
    for i, (example, prediction) in enumerate(zip(examples, result.predictions)):
        expected = example.get("expected_verdict", "PASS")
        predicted = prediction.get("verdict", "PASS")

        traces.append({
            "input": {
                "task": example.get("task", ""),
                "response": example.get("agent_response", ""),
            },
            "output": {
                "verdict": predicted,
                "reasoning": prediction.get("reasoning", ""),
            },
            "feedback": "CORRECT" if predicted == expected else f"INCORRECT: expected {expected}, got {predicted}",
            "correct_verdict": expected,
        })

    return traces
```

---

### 4. Reflective Update Meta-Prompt

**Current** (`prompt_proposer.yml`): Focuses on failure patterns and prompt engineering.

**Required**: Replace with a meta-prompt that matches the paper's exact structure.

**New `config/agents/reflective_updater.yml`**:

```yaml
spec: declarative_agent
spec_version: "0.4.0"

data:
  name: reflective-updater

  model:
    provider: cerebras
    name: zai-glm-4.6
    temperature: 0.7
    max_tokens: 8192

  system: |
    You are a prompt improvement specialist. Your task is to write improved
    instructions based on execution traces showing successes and failures.

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

    Your task: Write a new instruction for the assistant that will improve
    its performance based on the feedback above.

    Follow these steps:
    1. Identify the input format and detailed task description from the examples
    2. Extract all domain-specific factual information from the feedback
       (e.g., correct answers, edge cases, specific rules that were violated)
    3. Include any generalizable strategies the assistant used successfully
    4. Incorporate corrections for the failures shown in feedback

    Provide your new instructions within ''' blocks.

  output:
    new_instruction:
      type: str
      description: "The improved instruction, incorporating learnings from traces"
    factual_knowledge_extracted:
      type: list
      description: "Domain-specific facts learned from feedback"
      items:
        type: str
    strategies_preserved:
      type: list
      description: "Successful strategies kept from original"
      items:
        type: str
    corrections_made:
      type: list
      description: "Specific corrections based on failures"
      items:
        type: str

metadata:
  description: "GEPA-style reflective prompt mutation based on execution traces"
  tags: ["optimization", "gepa", "reflective-update"]
```

**Key differences from current**:
1. Uses **traces** (input/output/feedback) not aggregated failure patterns
2. Explicitly asks to **extract factual knowledge** from feedback
3. Asks to **preserve successful strategies**
4. Follows paper's exact structure

**Update `prompt_evolver.py`**:

```python
async def reflective_update(
    self,
    current_prompts: dict,
    traces: list[dict],
) -> PromptCandidate:
    """
    Paper's reflective update: mutate prompt based on traces.

    Args:
        current_prompts: Current judge config with system/user prompts
        traces: List of {input, output, feedback} from minibatch execution
    """
    data = current_prompts.get("data", {})
    current_instruction = f"SYSTEM:\n{data.get('system', '')}\n\nUSER TEMPLATE:\n{data.get('user', '')}"

    result = await self.reflective_updater.call(
        current_instruction=current_instruction,
        traces=traces,
    )

    # Parse new instruction back into system/user prompts
    new_instruction = result.get("new_instruction", "")
    system_prompt, user_prompt = self._parse_instruction(new_instruction)

    return PromptCandidate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        changes_made=result.get("corrections_made", []),
        expected_improvements="; ".join(result.get("factual_knowledge_extracted", [])),
        potential_risks="",
    )
```

---

### 5. Ancestry Tracking

**Paper** (Algorithm 1, step 2): `parents A <- [None]` - tracks parent for each candidate.

**Implementation** (add to `optimizer.py`):

```python
@dataclass
class AncestryTree:
    """Tracks the genetic lineage of candidates."""
    parents: dict[int, Optional[int]]  # candidate_id -> parent_id

    def add(self, candidate_id: int, parent_id: Optional[int]):
        self.parents[candidate_id] = parent_id

    def get_lineage(self, candidate_id: int) -> list[int]:
        """Get full ancestry chain from root to candidate."""
        lineage = []
        current = candidate_id
        while current is not None:
            lineage.append(current)
            current = self.parents.get(current)
        return list(reversed(lineage))

    def get_depth(self, candidate_id: int) -> int:
        """Get generation depth of candidate."""
        return len(self.get_lineage(candidate_id)) - 1

class GEPASelfOptimizer:
    def __init__(self, ...):
        # ... existing init ...
        self.population = Population(candidates=[], pareto_scores={})
        self.ancestry = AncestryTree(parents={})

    async def optimize(self, ...):
        # Initialize with base candidate
        base_config = self.current_judge_config
        base_scores = await self._evaluate_on_pareto(base_config, d_pareto)

        base_candidate = Candidate(
            id=0,
            config=base_config,
            parent_id=None,
            scores=base_scores,
        )
        self.population.add_candidate(base_candidate, base_scores)
        self.ancestry.add(0, None)

        # Main loop
        for iteration in range(budget):
            child = await self.run_iteration(
                iteration,
                self.population,
                d_feedback,
                d_pareto
            )

            if child:
                self.ancestry.add(child.id, child.parent_id)
                logger.info(f"New candidate {child.id} (depth {self.ancestry.get_depth(child.id)})")
```

**For logging/analysis**:

```python
def get_optimization_summary(self) -> dict:
    """Generate summary including ancestry information."""
    best_id = self._get_best_candidate_id()

    return {
        "best_candidate_id": best_id,
        "best_lineage": self.ancestry.get_lineage(best_id),
        "total_candidates": len(self.population.candidates),
        "max_depth": max(self.ancestry.get_depth(c.id) for c in self.population.candidates),
        "population_diversity": self._calculate_diversity(),
    }
```

---

### 6. Updated Main Loop

**Replace `optimizer.py` optimize method**:

```python
async def optimize(self, num_examples: int = 100, budget: int = 50) -> OptimizationResult:
    """
    GEPA-compliant optimization loop.

    Args:
        num_examples: Total examples to generate
        budget: Maximum iterations (LLM mutation calls)
    """
    start_time = datetime.now().isoformat()

    # Generate data
    examples = await self.generate_data(num_examples)

    # Step 1: Split into D_feedback, D_pareto, D_test
    d_feedback, d_pareto, d_test = self.split_data(examples)
    logger.info(f"Data split: {len(d_feedback)} feedback, {len(d_pareto)} pareto, {len(d_test)} test")

    # Step 2: Initialize population P with base system
    # Step 3: Evaluate base on D_pareto
    base_scores = await self._evaluate_on_pareto(self.current_judge_config, d_pareto)
    base_candidate = Candidate(
        id=0,
        config=self.current_judge_config,
        parent_id=None,
        scores=base_scores,
    )
    self.population.add_candidate(base_candidate, base_scores)
    self.ancestry.add(0, None)

    initial_avg = sum(base_scores.values()) / len(base_scores)
    logger.info(f"Base system average score on D_pareto: {initial_avg:.1f}%")

    # Step 4: Main loop
    for iteration in range(budget):
        logger.info(f"\n{'='*60}\nIteration {iteration + 1}/{budget}\n{'='*60}")
        logger.info(f"Population size: {len(self.population.candidates)}")

        child = await self.run_iteration(
            iteration,
            self.population,
            d_feedback,
            d_pareto,
        )

        if child:
            self.ancestry.add(child.id, child.parent_id)
            depth = self.ancestry.get_depth(child.id)
            avg_score = sum(child.scores.values()) / len(child.scores)
            logger.info(f"Added candidate {child.id} (depth {depth}, avg score {avg_score:.1f}%)")

    # Step 5: Select best candidate
    best_id = self._get_best_candidate_id(d_pareto)
    best_candidate = next(c for c in self.population.candidates if c.id == best_id)

    logger.info(f"\nBest candidate: {best_id}")
    logger.info(f"Lineage: {self.ancestry.get_lineage(best_id)}")

    # Final evaluation on D_test
    final_evaluator = JudgeEvaluator(judge_config_dict=best_candidate.config)
    final_result = await final_evaluator.evaluate_dataset(d_test)

    logger.info(f"Final test accuracy: {final_result.accuracy:.1f}%")

    # Save outputs
    self._save_results(best_candidate, final_result)

    return self._build_result(start_time, initial_avg, final_result)

def _get_best_candidate_id(self, d_pareto: list[dict]) -> int:
    """Return candidate with highest average score on D_pareto."""
    best_id = 0
    best_avg = -float('inf')

    for candidate in self.population.candidates:
        scores = self.population.pareto_scores[candidate.id]
        avg = sum(scores.values()) / len(scores)
        if avg > best_avg:
            best_avg = avg
            best_id = candidate.id

    return best_id
```

---

## Updated Architecture Diagram

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
|  |  |  Phi_0 |  |  Phi_1 |  |  Phi_2 |  |  Phi_3 |  ...              |   |
|  |  | (base) |  |        |  |        |  |        |                   |   |
|  |  +---+----+  +---+----+  +--------+  +--------+                   |   |
|  |      |           |                                                |   |
|  |      +-----+-----+  <- Ancestry Tree A                            |   |
|  |            v                                                      |   |
|  |   Per-instance scores S[Phi][i] on D_pareto                       |   |
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
|  |  3. Execute Phi_k on M        --> Gather traces + feedback        |   |
|  |           |                                                       |   |
|  |           v                                                       |   |
|  |  4. ReflectiveUpdate          --> LLM proposes mutation           |   |
|  |     (Reflective Updater)           using traces                   |   |
|  |           |                                                       |   |
|  |           v                                                       |   |
|  |  5. Evaluate Phi' on M        --> Minibatch gating                |   |
|  |           |                                                       |   |
|  |           v                                                       |   |
|  |  6. If improved on M:                                             |   |
|  |     - Evaluate Phi' on D_pareto                                   |   |
|  |     - Add to P, record parent in A                                |   |
|  |                                                                   |   |
|  +------------------------------------------------------------------+   |
|                           |                                              |
|                           v                                              |
|  +------------------------------------------------------------------+   |
|  |                       Output                                      |   |
|  |  - Best Phi* = argmax avg score on D_pareto                       |   |
|  |  - Final eval on D_test                                           |   |
|  |  - Ancestry lineage of winning candidate                          |   |
|  +------------------------------------------------------------------+   |
+-------------------------------------------------------------------------+
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/optimizer.py` | Replace with population-based loop, add Pareto selection, ancestry tracking |
| `src/prompt_evolver.py` | Add `reflective_update()` method, remove `rank_candidates()` |
| `src/evaluator.py` | Add `evaluate_on_pareto()` returning per-instance scores |
| `config/agents/prompt_proposer.yml` | Replace with `reflective_updater.yml` matching paper's meta-prompt |
| `config/agents/candidate_ranker.yml` | **DELETE** - Pareto selection is algorithmic, not LLM-based |
| `config/agents/failure_analyzer.yml` | **DELETE** - traces replace explicit failure analysis |

---

## New Config Parameters

```yaml
# config/settings.yml
optimization:
  budget: 50                # Total mutation attempts
  pareto_set_size: 30       # |D_pareto|
  minibatch_size: 5         # |M| for gating
  test_split: 0.2           # Fraction held out for final test
```

---

## Agents After Changes

| Agent | Status |
|-------|--------|
| `judge.yml` | Keep (target of optimization) |
| `task_generator.yml` | Keep (data generation) |
| `response_generator.yml` | Keep (data generation) |
| `failure_analyzer.yml` | **Remove** - traces replace explicit failure analysis |
| `prompt_proposer.yml` | **Replace** with `reflective_updater.yml` |
| `candidate_ranker.yml` | **Remove** - Pareto selection is algorithmic |
| `summary_generator.yml` | Keep (reporting) |

---

## Implementation Priority

### High Priority (algorithmic correctness)
1. Pareto population + SelectCandidate algorithm
2. Data split (D_feedback / D_pareto / D_test)
3. Minibatch gating

### Medium Priority (efficiency + paper compliance)
4. Reflective update meta-prompt
5. Ancestry tracking

### Low Priority (cleanup)
6. Remove unused agents
7. Update documentation
