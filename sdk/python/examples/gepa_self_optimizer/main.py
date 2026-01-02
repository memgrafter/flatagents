#!/usr/bin/env python3
"""
GEPA Self-Optimizer

Optimizes a GEPA judge using flatagents for all LLM calls.

Usage:
    python main.py run                    # Full pipeline
    python main.py generate-data          # Generate evaluation data only
    python main.py evaluate               # Evaluate current judge only
    python main.py optimize               # Run optimization only (requires existing data)
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from flatagents import setup_logging, get_logger
from src.optimizer import GEPASelfOptimizer, OptimizationConfig
from src.data_generator import DataGenerator
from src.evaluator import JudgeEvaluator
from src.utils import load_json

# Configure logging
setup_logging(level='INFO')
logger = get_logger(__name__)


def get_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        description="GEPA Self-Optimizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Run command - full pipeline
    run_parser = subparsers.add_parser("run", help="Run full optimization pipeline")
    run_parser.add_argument("--num-examples", type=int, default=100,
                           help="Number of evaluation examples")
    run_parser.add_argument("--budget", type=int, default=50,
                           help="Maximum mutation attempts (GEPA budget B)")
    run_parser.add_argument("--pareto-size", type=int, default=30,
                           help="Size of D_pareto for candidate scoring")
    run_parser.add_argument("--minibatch-size", type=int, default=5,
                           help="Size of minibatch for mutation feedback")
    run_parser.add_argument("--force-regenerate", action="store_true",
                           help="Force regenerate evaluation data")

    # Generate data command
    gen_parser = subparsers.add_parser("generate-data", help="Generate evaluation data")
    gen_parser.add_argument("--num-examples", type=int, default=50,
                           help="Number of examples to generate")
    gen_parser.add_argument("--correct-ratio", type=float, default=0.3,
                           help="Ratio of correct (no error) examples")
    gen_parser.add_argument("--output", type=Path, default=None,
                           help="Output path for data")

    # Evaluate command
    eval_parser = subparsers.add_parser("evaluate", help="Evaluate judge on data")
    eval_parser.add_argument("--judge", type=Path, default=None,
                            help="Path to judge config (default: config/agents/judge.yml)")
    eval_parser.add_argument("--data", type=Path, default=None,
                            help="Path to evaluation data")

    # Optimize command
    opt_parser = subparsers.add_parser("optimize", help="Run optimization (requires existing data)")
    opt_parser.add_argument("--budget", type=int, default=50,
                           help="Maximum mutation attempts (GEPA budget B)")
    opt_parser.add_argument("--pareto-size", type=int, default=30,
                           help="Size of D_pareto for candidate scoring")
    opt_parser.add_argument("--minibatch-size", type=int, default=5,
                           help="Size of minibatch for mutation feedback")

    return parser


async def cmd_run(args):
    """Run full GEPA optimization pipeline."""
    logger.info("Starting GEPA optimization pipeline")

    config = OptimizationConfig(
        budget=args.budget,
        pareto_set_size=args.pareto_size,
        minibatch_size=args.minibatch_size,
    )

    optimizer = GEPASelfOptimizer(
        config_dir=PROJECT_ROOT / "config",
        output_dir=PROJECT_ROOT / "output",
        config=config,
    )

    result = await optimizer.optimize(
        num_examples=args.num_examples,
        force_regenerate_data=args.force_regenerate,
    )

    logger.info("=" * 60)
    logger.info("GEPA OPTIMIZATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Initial accuracy:   {result.initial_accuracy:.1f}%")
    logger.info(f"Final accuracy:     {result.final_accuracy:.1f}%")
    logger.info(f"Improvement:        {result.total_improvement:+.1f}%")
    logger.info(f"Iterations:         {len(result.iterations)}")
    logger.info(f"Population size:    {result.population_size}")
    logger.info(f"Best candidate:     {result.best_candidate_id}")
    logger.info(f"Best lineage:       {result.best_lineage}")
    logger.info(f"Total LLM calls:    {result.total_llm_calls}")
    logger.info(f"Estimated cost:     ${result.total_cost:.4f}")
    logger.info(f"Optimized judge saved to: output/optimized_judge.yml")


async def cmd_generate_data(args):
    """Generate evaluation data."""
    logger.info(f"Generating {args.num_examples} evaluation examples")

    generator = DataGenerator(PROJECT_ROOT / "config")

    examples = await generator.generate_dataset(
        num_examples=args.num_examples,
        correct_ratio=args.correct_ratio,
    )

    output_path = args.output or (PROJECT_ROOT / "data" / "evaluation_set.json")
    generator.save_dataset(examples, output_path)

    stats = generator.get_stats()

    logger.info("=" * 60)
    logger.info("DATA GENERATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Examples generated: {len(examples)}")
    logger.info(f"Output path: {output_path}")
    logger.info(f"Task generator calls: {stats['task_generator_calls']}")
    logger.info(f"Response generator calls: {stats['response_generator_calls']}")

    # Show distribution
    verdicts = {}
    domains = {}
    for ex in examples:
        v = ex.get("expected_verdict", "PASS")
        d = ex.get("domain", "unknown")
        verdicts[v] = verdicts.get(v, 0) + 1
        domains[d] = domains.get(d, 0) + 1

    logger.info(f"Verdict distribution: {verdicts}")
    logger.info(f"Domain distribution: {domains}")


async def cmd_evaluate(args):
    """Evaluate judge on data."""

    judge_path = args.judge or (PROJECT_ROOT / "config" / "agents" / "judge.yml")
    data_path = args.data or (PROJECT_ROOT / "data" / "evaluation_set.json")

    if not data_path.exists():
        logger.error(f"Data file not found: {data_path}")
        logger.info("Run 'python main.py generate-data' first")
        return

    logger.info(f"Evaluating judge: {judge_path}")
    logger.info(f"Using data: {data_path}")

    evaluator = JudgeEvaluator(judge_config_path=judge_path)
    examples = load_json(data_path)

    result = await evaluator.evaluate_dataset(examples)

    logger.info("=" * 60)
    logger.info("EVALUATION RESULTS")
    logger.info("=" * 60)
    logger.info(f"Judge: {judge_path.name}")
    logger.info(f"Examples: {len(examples)}")
    logger.info(f"Accuracy:           {result.accuracy:.1f}%")
    logger.info(f"Balanced Accuracy:  {result.balanced_accuracy:.1f}%")
    logger.info(f"False Positive Rate: {result.false_positive_rate:.1f}%")
    logger.info(f"False Negative Rate: {result.false_negative_rate:.1f}%")
    logger.info(f"Calibration Error:  {result.calibration_error:.3f}")
    logger.info(f"Failures: {len(result.failures)}")
    logger.info(f"API calls: {result.total_calls}")
    logger.info(f"Estimated cost: ${result.total_cost:.4f}")

    if result.failures:
        logger.info("Sample failures:")
        for failure in result.failures[:3]:
            logger.info(f"  - Expected: {failure['expected_verdict']}, "
                      f"Got: {failure['predicted_verdict']}")


async def cmd_optimize(args):
    """Run GEPA optimization only (requires existing data)."""

    data_path = PROJECT_ROOT / "data" / "evaluation_set.json"
    if not data_path.exists():
        logger.error(f"Data file not found: {data_path}")
        logger.info("Run 'python main.py generate-data' first")
        return

    config = OptimizationConfig(
        budget=args.budget,
        pareto_set_size=args.pareto_size,
        minibatch_size=args.minibatch_size,
    )

    optimizer = GEPASelfOptimizer(
        config_dir=PROJECT_ROOT / "config",
        output_dir=PROJECT_ROOT / "output",
        config=config,
    )

    result = await optimizer.optimize(
        num_examples=100,  # Will load from file
        force_regenerate_data=False,
    )

    logger.info("=" * 60)
    logger.info("GEPA OPTIMIZATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Initial accuracy:   {result.initial_accuracy:.1f}%")
    logger.info(f"Final accuracy:     {result.final_accuracy:.1f}%")
    logger.info(f"Improvement:        {result.total_improvement:+.1f}%")
    logger.info(f"Population size:    {result.population_size}")
    logger.info(f"Best candidate:     {result.best_candidate_id}")


def main():
    """Main entry point."""
    parser = get_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Run the appropriate command
    if args.command == "run":
        asyncio.run(cmd_run(args))
    elif args.command == "generate-data":
        asyncio.run(cmd_generate_data(args))
    elif args.command == "evaluate":
        asyncio.run(cmd_evaluate(args))
    elif args.command == "optimize":
        asyncio.run(cmd_optimize(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
