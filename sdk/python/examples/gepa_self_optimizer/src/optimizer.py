"""
Main GEPA self-optimizer implementing the paper's core algorithm.

Implements Algorithm 1 (Main Loop) and Algorithm 2 (Pareto-Based Candidate Selection)
from the GEPA paper. All LLM calls are made through flatagents.
"""

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .data_generator import DataGenerator
from .evaluator import JudgeEvaluator, EvaluationResult
from .prompt_evolver import PromptEvolver, PromptCandidate
from .utils import load_yaml, save_yaml, load_json, save_json, load_agent
from flatagents import setup_logging, get_logger

# Configure logging
setup_logging(level='INFO')
logger = get_logger(__name__)


# =============================================================================
# GEPA Configuration
# =============================================================================

@dataclass
class OptimizationConfig:
    """
    Configuration for the GEPA optimization run.

    Hyperparameters from the paper:
    - budget: Maximum number of mutation attempts (B in Algorithm 1)
    - pareto_set_size: Size of D_pareto for candidate scoring (n_pareto)
    - minibatch_size: Size of minibatch M for mutation feedback (b)
    """
    budget: int = 50                    # Maximum iterations (LLM mutation calls)
    pareto_set_size: int = 30           # |D_pareto| - paper recommends 20-50
    minibatch_size: int = 5             # |M| for minibatch evaluation
    test_split: float = 0.2             # Fraction held out for final test
    early_stop_patience: int = 10       # Stop if no new candidates for N iterations


# =============================================================================
# Core Data Structures (Algorithm 1 & 2)
# =============================================================================

@dataclass
class Candidate:
    """
    A candidate system configuration.

    From Algorithm 1:
    - Each candidate Φ is a system configuration (judge prompts)
    - Tracks parent for ancestry (A in Algorithm 1, step 2)
    - Stores per-instance scores on D_pareto (S[Φ] in Algorithm 1)
    """
    id: int
    config: dict
    parent_id: Optional[int]  # For ancestry tracking (A)
    scores: dict[int, float] = field(default_factory=dict)  # instance_idx -> score


@dataclass
class Population:
    """
    Population of candidates with per-instance scores.

    From Algorithm 1:
    - P: list of all candidates
    - S: scores for each candidate on each D_pareto instance
    """
    candidates: list[Candidate] = field(default_factory=list)
    pareto_scores: dict[int, dict[int, float]] = field(default_factory=dict)  # candidate_id -> {instance_idx -> score}

    def add_candidate(self, candidate: Candidate, scores: dict[int, float]) -> None:
        """Add a candidate with its per-instance scores."""
        self.candidates.append(candidate)
        self.pareto_scores[candidate.id] = scores
        candidate.scores = scores


@dataclass
class AncestryTree:
    """
    Tracks the genetic lineage of candidates.

    From Algorithm 1, step 2: parents A ← [None]
    Each candidate records its parent, enabling accumulated learning.
    """
    parents: dict[int, Optional[int]] = field(default_factory=dict)  # candidate_id -> parent_id

    def add(self, candidate_id: int, parent_id: Optional[int]) -> None:
        """Record parent for a candidate."""
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


# =============================================================================
# Result Data Structures
# =============================================================================

@dataclass
class IterationResult:
    """Results from a single GEPA iteration."""
    iteration: int
    parent_id: int
    child_id: Optional[int]  # None if child wasn't promoted
    parent_minibatch_score: float
    child_minibatch_score: Optional[float]
    promoted: bool
    child_pareto_avg: Optional[float]


@dataclass
class OptimizationResult:
    """Results from the full GEPA optimization run."""
    start_time: str
    end_time: str
    initial_accuracy: float
    final_accuracy: float
    total_improvement: float
    iterations: list[IterationResult]
    final_config: dict
    best_candidate_id: int
    best_lineage: list[int]
    population_size: int
    total_llm_calls: int
    total_cost: float

    def to_dict(self) -> dict:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "initial_accuracy": self.initial_accuracy,
            "final_accuracy": self.final_accuracy,
            "total_improvement": self.total_improvement,
            "num_iterations": len(self.iterations),
            "iterations": [
                {
                    "iteration": r.iteration,
                    "parent_id": r.parent_id,
                    "child_id": r.child_id,
                    "promoted": r.promoted,
                    "child_pareto_avg": r.child_pareto_avg,
                }
                for r in self.iterations
            ],
            "best_candidate_id": self.best_candidate_id,
            "best_lineage": self.best_lineage,
            "population_size": self.population_size,
            "total_llm_calls": self.total_llm_calls,
            "total_cost": self.total_cost,
        }


# =============================================================================
# Main GEPA Optimizer
# =============================================================================

class GEPASelfOptimizer:
    """
    Main optimizer implementing GEPA Algorithm 1 and Algorithm 2.

    All LLM calls are made through flatagents:
    - Judge agent (target of optimization)
    - Task generator agent (for data generation)
    - Response generator agent (for data generation)
    - Reflective updater agent (for prompt mutation)
    - Summary generator agent (for reporting)
    """

    def __init__(
        self,
        config_dir: Path,
        output_dir: Path,
        config: Optional[OptimizationConfig] = None,
    ):
        """
        Initialize the optimizer.

        Args:
            config_dir: Path to config directory containing agents/
            output_dir: Path to output directory for results
            config: Optimization configuration
        """
        self.config_dir = Path(config_dir)
        self.output_dir = Path(output_dir)
        self.config = config or OptimizationConfig()

        self.agents_dir = self.config_dir / "agents"
        self.data_dir = self.config_dir.parent / "data"

        # Initialize components (flatagents loaded within)
        self.data_generator = DataGenerator(self.config_dir)
        self.prompt_evolver = PromptEvolver(self.config_dir)

        # Load summary generator for final report
        self.summary_generator = load_agent(self.agents_dir / "summary_generator.yml")

        # Load initial judge config
        self.judge_config_path = self.agents_dir / "judge.yml"
        self.current_judge_config = load_yaml(self.judge_config_path)

        # GEPA state (Algorithm 1, step 2)
        self.population = Population()
        self.ancestry = AncestryTree()

        # Tracking
        self.iterations: list[IterationResult] = []
        self.total_llm_calls = 0
        self.total_cost = 0.0

        logger.info("GEPASelfOptimizer initialized with GEPA algorithm")

    # =========================================================================
    # Data Management
    # =========================================================================

    async def generate_data(
        self,
        num_examples: int = 100,
        force_regenerate: bool = False,
    ) -> list[dict]:
        """Generate or load evaluation data."""
        data_path = self.data_dir / "evaluation_set.json"

        if data_path.exists() and not force_regenerate:
            logger.info(f"Loading existing data from {data_path}")
            return load_json(data_path)

        logger.info(f"Generating {num_examples} evaluation examples")
        examples = await self.data_generator.generate_dataset(num_examples)

        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)
        save_json(examples, data_path)

        return examples

    def split_data(
        self,
        examples: list[dict],
    ) -> tuple[list[dict], list[dict], list[dict]]:
        """
        Split data into D_feedback, D_pareto, and D_test.

        From Algorithm 1, step 1:
        - D_feedback: Used for minibatch sampling during mutation (large)
        - D_pareto: Used for candidate scoring/selection (small, fixed)
        - D_test: Held out for final evaluation

        Args:
            examples: All evaluation examples

        Returns:
            Tuple of (d_feedback, d_pareto, d_test)
        """
        n = len(examples)
        n_pareto = min(self.config.pareto_set_size, n // 3)
        n_test = int(n * self.config.test_split)

        # Shuffle to ensure random split
        shuffled = examples.copy()
        random.shuffle(shuffled)

        d_test = shuffled[:n_test]
        d_pareto = shuffled[n_test:n_test + n_pareto]
        d_feedback = shuffled[n_test + n_pareto:]

        return d_feedback, d_pareto, d_test

    # =========================================================================
    # Algorithm 2: Pareto-Based Candidate Selection
    # =========================================================================

    def select_candidate(self, d_pareto: list[dict]) -> int:
        """
        Pareto-based candidate selection (Algorithm 2).

        Steps:
        1. Find best candidates per instance
        2. Collect Pareto frontier (candidates best on at least one instance)
        3. Remove dominated candidates
        4. Sample by frequency (count of instances where candidate achieves best)

        Returns:
            ID of selected candidate for mutation
        """
        n_instances = len(d_pareto)

        if len(self.population.candidates) == 1:
            return self.population.candidates[0].id

        # Step 1: Find best candidates per instance
        best_per_instance: dict[int, list[int]] = {}  # instance -> [candidate_ids with best score]

        for i in range(n_instances):
            best_score = -float('inf')
            best_candidates = []

            for candidate in self.population.candidates:
                score = self.population.pareto_scores[candidate.id].get(i, 0)
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
        for a_id in list(frontier_ids):
            for b_id in list(frontier_ids):
                if a_id == b_id:
                    continue
                if self._dominates(a_id, b_id, n_instances):
                    non_dominated.discard(b_id)

        # If all dominated (shouldn't happen), fall back to all candidates
        if not non_dominated:
            non_dominated = frontier_ids

        # Step 4: Sample by frequency (count of instances where candidate achieves best)
        frequency: dict[int, int] = {cid: 0 for cid in non_dominated}
        for instance_bests in best_per_instance.values():
            for cid in instance_bests:
                if cid in frequency:
                    frequency[cid] += 1

        # Weighted random sample
        candidates_list = list(frequency.keys())
        weights = [frequency[cid] for cid in candidates_list]
        total = sum(weights)

        if total == 0:
            # Uniform if no wins
            selected_id = random.choice(candidates_list)
        else:
            weights = [w / total for w in weights]
            selected_id = random.choices(candidates_list, weights=weights, k=1)[0]

        return selected_id

    def _dominates(self, a_id: int, b_id: int, n_instances: int) -> bool:
        """
        Check if candidate A dominates candidate B.

        A dominates B if:
        - A >= B on all instances, AND
        - A > B on at least one instance
        """
        dominated = True
        strictly_better = False

        for i in range(n_instances):
            a_score = self.population.pareto_scores[a_id].get(i, 0)
            b_score = self.population.pareto_scores[b_id].get(i, 0)

            if a_score < b_score:
                dominated = False
                break
            if a_score > b_score:
                strictly_better = True

        return dominated and strictly_better

    # =========================================================================
    # Per-Instance Evaluation for D_pareto
    # =========================================================================

    async def evaluate_on_pareto(
        self,
        config: dict,
        d_pareto: list[dict],
    ) -> dict[int, float]:
        """
        Evaluate a candidate on D_pareto, returning per-instance scores.

        Args:
            config: Judge configuration to evaluate
            d_pareto: The pareto evaluation set

        Returns:
            Dictionary mapping instance index to score (1.0 for correct, 0.0 for incorrect)
        """
        evaluator = JudgeEvaluator(judge_config_dict=config)
        scores = {}

        for i, example in enumerate(d_pareto):
            prediction = await evaluator.evaluate_single(example)
            prediction_output = prediction.output or {}
            expected = example.get("expected_verdict", "PASS")
            predicted = prediction_output.get("verdict", "PASS")

            # Binary score: 1.0 if correct, 0.0 if incorrect
            scores[i] = 1.0 if predicted == expected else 0.0

        return scores

    # =========================================================================
    # Trace Gathering for Reflective Update
    # =========================================================================

    def _gather_traces(
        self,
        examples: list[dict],
        result: EvaluationResult,
    ) -> list[dict]:
        """
        Gather (input, output, feedback) traces for reflective update.

        This is the format expected by the GEPA reflective meta-prompt.
        """
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

    # =========================================================================
    # Algorithm 1: Main GEPA Iteration
    # =========================================================================

    async def run_iteration(
        self,
        iteration: int,
        d_feedback: list[dict],
        d_pareto: list[dict],
    ) -> IterationResult:
        """
        Run a single GEPA iteration (Algorithm 1, step 4).

        Steps:
        4a. SelectCandidate(P, S) - Pareto sampling
        4b. SelectModule - N/A for single module
        4c. Sample minibatch M from D_feedback
        4d. Execute parent on M, gather traces and feedback
        4e. ReflectiveUpdate to propose mutation
        4f. Create child candidate
        4g. If improved on M: add to P, evaluate on D_pareto

        Returns:
            IterationResult with outcome of this iteration
        """
        # Step 4a: Select candidate from population via Pareto sampling
        parent_id = self.select_candidate(d_pareto)
        parent = next(c for c in self.population.candidates if c.id == parent_id)

        logger.info(f"Selected parent candidate {parent_id} for mutation")

        # Step 4c: Sample minibatch M from D_feedback
        minibatch_size = min(self.config.minibatch_size, len(d_feedback))
        minibatch = random.sample(d_feedback, minibatch_size)

        # Step 4d: Execute parent on minibatch, gather traces and feedback
        parent_evaluator = JudgeEvaluator(judge_config_dict=parent.config)
        parent_minibatch_result = await parent_evaluator.evaluate_dataset(
            minibatch, show_progress=False
        )
        parent_minibatch_score = parent_minibatch_result.accuracy

        logger.info(f"Parent score on minibatch: {parent_minibatch_score:.1f}%")

        # If parent is perfect on minibatch, skip mutation
        if not parent_minibatch_result.failures:
            logger.info("Parent perfect on minibatch, skipping mutation")
            return IterationResult(
                iteration=iteration,
                parent_id=parent_id,
                child_id=None,
                parent_minibatch_score=parent_minibatch_score,
                child_minibatch_score=None,
                promoted=False,
                child_pareto_avg=None,
            )

        # Gather traces for reflective update
        traces = self._gather_traces(minibatch, parent_minibatch_result)

        # Step 4e: ReflectiveUpdate - propose mutation based on traces
        candidate_prompt = await self.prompt_evolver.reflective_update(
            current_config=parent.config,
            traces=traces,
        )

        # Step 4f: Create child candidate config
        child_config = self.prompt_evolver.create_candidate_config(
            parent.config, candidate_prompt
        )

        # Evaluate child on SAME minibatch
        child_evaluator = JudgeEvaluator(judge_config_dict=child_config)
        child_minibatch_result = await child_evaluator.evaluate_dataset(
            minibatch, show_progress=False
        )
        child_minibatch_score = child_minibatch_result.accuracy

        logger.info(f"Child score on minibatch: {child_minibatch_score:.1f}%")

        # Step 4g: Only promote if improved on minibatch
        if child_minibatch_score <= parent_minibatch_score:
            logger.info(
                f"Child ({child_minibatch_score:.1f}%) did not improve on "
                f"parent ({parent_minibatch_score:.1f}%) - not promoting"
            )
            return IterationResult(
                iteration=iteration,
                parent_id=parent_id,
                child_id=None,
                parent_minibatch_score=parent_minibatch_score,
                child_minibatch_score=child_minibatch_score,
                promoted=False,
                child_pareto_avg=None,
            )

        logger.info(
            f"Child improved: {parent_minibatch_score:.1f}% -> "
            f"{child_minibatch_score:.1f}% - promoting to population"
        )

        # Promote: Evaluate on full D_pareto
        child_pareto_scores = await self.evaluate_on_pareto(child_config, d_pareto)
        child_pareto_avg = sum(child_pareto_scores.values()) / len(child_pareto_scores) * 100

        # Create and add child to population
        child_id = len(self.population.candidates)
        child = Candidate(
            id=child_id,
            config=child_config,
            parent_id=parent_id,
            scores=child_pareto_scores,
        )

        self.population.add_candidate(child, child_pareto_scores)
        self.ancestry.add(child_id, parent_id)

        logger.info(
            f"Added candidate {child_id} to population "
            f"(depth {self.ancestry.get_depth(child_id)}, "
            f"pareto avg {child_pareto_avg:.1f}%)"
        )

        return IterationResult(
            iteration=iteration,
            parent_id=parent_id,
            child_id=child_id,
            parent_minibatch_score=parent_minibatch_score,
            child_minibatch_score=child_minibatch_score,
            promoted=True,
            child_pareto_avg=child_pareto_avg,
        )

    # =========================================================================
    # Algorithm 1: Main Optimization Loop
    # =========================================================================

    async def optimize(
        self,
        num_examples: int = 100,
        force_regenerate_data: bool = False,
    ) -> OptimizationResult:
        """
        Run the full GEPA optimization loop (Algorithm 1).

        Args:
            num_examples: Total examples to generate
            force_regenerate_data: Whether to regenerate evaluation data

        Returns:
            OptimizationResult with full history and final config
        """
        start_time = datetime.now().isoformat()

        # Generate/load data
        examples = await self.generate_data(num_examples, force_regenerate_data)

        # Step 1: Split into D_feedback, D_pareto, D_test
        d_feedback, d_pareto, d_test = self.split_data(examples)
        logger.info(
            f"Data split: {len(d_feedback)} feedback, "
            f"{len(d_pareto)} pareto, {len(d_test)} test"
        )

        # Step 2: Initialize candidates P ← [Φ], parents A ← [None]
        # Step 3: Evaluate base system on D_pareto → S[Φ]
        base_scores = await self.evaluate_on_pareto(self.current_judge_config, d_pareto)
        base_candidate = Candidate(
            id=0,
            config=self.current_judge_config,
            parent_id=None,
            scores=base_scores,
        )
        self.population.add_candidate(base_candidate, base_scores)
        self.ancestry.add(0, None)

        initial_pareto_avg = sum(base_scores.values()) / len(base_scores) * 100
        logger.info(f"Base system average score on D_pareto: {initial_pareto_avg:.1f}%")

        # Evaluate on test set for reporting
        initial_evaluator = JudgeEvaluator(judge_config_dict=self.current_judge_config)
        initial_result = await initial_evaluator.evaluate_dataset(d_test, show_progress=False)
        initial_accuracy = initial_result.accuracy
        logger.info(f"Initial test accuracy: {initial_accuracy:.1f}%")

        # Step 4: Main loop - while budget B not exhausted
        no_new_candidates = 0

        for iteration in range(1, self.config.budget + 1):
            logger.info(f"\n{'='*60}\nIteration {iteration}/{self.config.budget}\n{'='*60}")
            logger.info(f"Population size: {len(self.population.candidates)}")

            result = await self.run_iteration(iteration, d_feedback, d_pareto)
            self.iterations.append(result)

            # Early stopping if no new candidates for a while
            if result.promoted:
                no_new_candidates = 0
            else:
                no_new_candidates += 1
                if no_new_candidates >= self.config.early_stop_patience:
                    logger.info(
                        f"Early stopping: no new candidates for "
                        f"{no_new_candidates} iterations"
                    )
                    break

        # Step 5: Return candidate maximizing average score on D_pareto
        best_id = self._get_best_candidate_id()
        best_candidate = next(c for c in self.population.candidates if c.id == best_id)
        best_lineage = self.ancestry.get_lineage(best_id)

        logger.info(f"\nBest candidate: {best_id}")
        logger.info(f"Lineage: {best_lineage}")

        # Final evaluation on D_test
        final_evaluator = JudgeEvaluator(judge_config_dict=best_candidate.config)
        final_result = await final_evaluator.evaluate_dataset(d_test, show_progress=False)
        final_accuracy = final_result.accuracy

        logger.info(f"Final test accuracy: {final_accuracy:.1f}%")
        logger.info(f"Total improvement: {final_accuracy - initial_accuracy:.1f}%")

        # Update totals
        self._update_totals()

        # Save optimized config
        self.output_dir.mkdir(parents=True, exist_ok=True)
        optimized_path = self.output_dir / "optimized_judge.yml"
        save_yaml(best_candidate.config, optimized_path)
        logger.info(f"Saved optimized judge to {optimized_path}")

        end_time = datetime.now().isoformat()

        result = OptimizationResult(
            start_time=start_time,
            end_time=end_time,
            initial_accuracy=initial_accuracy,
            final_accuracy=final_accuracy,
            total_improvement=final_accuracy - initial_accuracy,
            iterations=self.iterations,
            final_config=best_candidate.config,
            best_candidate_id=best_id,
            best_lineage=best_lineage,
            population_size=len(self.population.candidates),
            total_llm_calls=self.total_llm_calls,
            total_cost=self.total_cost,
        )

        # Save optimization log
        log_path = self.output_dir / "optimization_log.json"
        save_json(result.to_dict(), log_path)
        logger.info(f"Saved optimization log to {log_path}")

        # Generate summary
        await self._generate_summary(result)

        return result

    def _get_best_candidate_id(self) -> int:
        """Return candidate with highest average score on D_pareto."""
        best_id = 0
        best_avg = -float('inf')

        for candidate in self.population.candidates:
            scores = self.population.pareto_scores[candidate.id]
            if not scores:
                continue
            avg = sum(scores.values()) / len(scores)
            if avg > best_avg:
                best_avg = avg
                best_id = candidate.id

        return best_id

    async def _generate_summary(self, result: OptimizationResult) -> None:
        """Generate a summary of the optimization run."""
        promoted_iterations = [r for r in result.iterations if r.promoted]

        summary_result = await self.summary_generator.call(
            num_iterations=len(result.iterations),
            total_calls=result.total_llm_calls,
            num_examples=len(self.population.candidates),
            iterations=[
                {
                    "iteration": r.iteration,
                    "promoted": r.promoted,
                    "pareto_avg": r.child_pareto_avg,
                }
                for r in promoted_iterations[:10]
            ],
            start_accuracy=result.initial_accuracy,
            final_accuracy=result.final_accuracy,
            improvement=result.total_improvement,
            key_changes=[f"Candidate {r.child_id} from parent {r.parent_id}" for r in promoted_iterations[:5]],
        )

        # Save summary
        summary_path = self.output_dir / "summary.json"
        summary_output = summary_result.output or {}
        save_json(summary_output, summary_path)

        logger.info(f"Summary: {summary_output.get('summary', '')[:500]}")

    def _update_totals(self) -> None:
        """Update total LLM calls and costs."""
        # Data generator stats
        gen_stats = self.data_generator.get_stats()
        self.total_llm_calls += gen_stats.get("task_generator_calls", 0)
        self.total_llm_calls += gen_stats.get("response_generator_calls", 0)
        self.total_cost += gen_stats.get("task_generator_cost", 0)
        self.total_cost += gen_stats.get("response_generator_cost", 0)

        # Prompt evolver stats
        evolver_stats = self.prompt_evolver.get_stats()
        self.total_llm_calls += evolver_stats.get("reflective_updater_calls", 0)
        self.total_cost += evolver_stats.get("reflective_updater_cost", 0)

        # Summary generator
        self.total_llm_calls += self.summary_generator.total_api_calls
        self.total_cost += self.summary_generator.total_cost
