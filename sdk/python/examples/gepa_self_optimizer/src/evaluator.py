"""
Judge evaluator using flatagents.

Runs the judge on evaluation data and calculates metrics.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from flatagents import setup_logging, get_logger
from .utils import (
    load_agent,
    load_json,
    create_agent_from_dict,
    calculate_accuracy,
    calculate_false_positive_rate,
    calculate_false_negative_rate,
    calculate_calibration_error,
)

# Configure logging
setup_logging(level='INFO')
logger = get_logger(__name__)


@dataclass
class EvaluationResult:
    """Results from evaluating a judge."""
    accuracy: float
    false_positive_rate: float
    false_negative_rate: float
    calibration_error: float
    predictions: list[dict]
    failures: list[dict]  # Cases where judge disagreed with ground truth
    total_calls: int
    total_cost: float

    @property
    def balanced_accuracy(self) -> float:
        """Calculate balanced accuracy (average of TPR and TNR)."""
        tpr = 100 - self.false_negative_rate
        tnr = 100 - self.false_positive_rate
        return (tpr + tnr) / 2

    def to_dict(self) -> dict:
        return {
            "accuracy": self.accuracy,
            "balanced_accuracy": self.balanced_accuracy,
            "false_positive_rate": self.false_positive_rate,
            "false_negative_rate": self.false_negative_rate,
            "calibration_error": self.calibration_error,
            "num_failures": len(self.failures),
            "total_calls": self.total_calls,
            "total_cost": self.total_cost,
        }


class JudgeEvaluator:
    """Evaluates a judge agent on evaluation data."""

    def __init__(
        self,
        judge_config_path: Optional[Path] = None,
        judge_config_dict: Optional[dict] = None,
    ):
        """
        Initialize with either a config file path or a config dictionary.

        Args:
            judge_config_path: Path to judge.yml config file
            judge_config_dict: Judge config as dictionary (for testing modified prompts)
        """
        if judge_config_path:
            self.judge = load_agent(judge_config_path)
            self.judge_config = self._load_config(judge_config_path)
        elif judge_config_dict:
            self.judge = create_agent_from_dict(judge_config_dict)
            self.judge_config = judge_config_dict
        else:
            raise ValueError("Must provide either judge_config_path or judge_config_dict")

        logger.info("JudgeEvaluator initialized")

    def _load_config(self, path: Path) -> dict:
        """Load the judge config for inspection."""
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)

    async def evaluate_single(self, example: dict) -> dict:
        """
        Evaluate a single example using the judge.

        Args:
            example: Evaluation example with task, agent_response, etc.

        Returns:
            Judge's prediction including verdict, reasoning, confidence
        """
        result = await self.judge.call(
            task=example.get("task", ""),
            response=example.get("agent_response", ""),
            context=example.get("evaluation_criteria", ""),
        )
        return result

    async def evaluate_dataset(
        self,
        examples: list[dict],
        show_progress: bool = True,
    ) -> EvaluationResult:
        """
        Evaluate the judge on a full dataset.

        Args:
            examples: List of evaluation examples with ground truth
            show_progress: Whether to log progress

        Returns:
            EvaluationResult with metrics and failure cases
        """
        predictions = []
        failures = []

        for i, example in enumerate(examples):
            if show_progress:
                logger.info(f"Evaluating example {i+1}/{len(examples)}")

            prediction = await self.evaluate_single(example)
            prediction_output = prediction.output or {}
            predictions.append(prediction_output)

            # Check if this is a failure case
            expected = example.get("expected_verdict", "PASS")
            predicted = prediction_output.get("verdict", "PASS")

            if predicted != expected:
                failures.append({
                    "example": example,
                    "prediction": prediction,
                    "expected_verdict": expected,
                    "predicted_verdict": predicted,
                })

        # Create ground truth list for metric calculation
        ground_truth = [{"expected_verdict": e.get("expected_verdict", "PASS")} for e in examples]

        # Calculate metrics
        result = EvaluationResult(
            accuracy=calculate_accuracy(predictions, ground_truth),
            false_positive_rate=calculate_false_positive_rate(predictions, ground_truth),
            false_negative_rate=calculate_false_negative_rate(predictions, ground_truth),
            calibration_error=calculate_calibration_error(predictions, ground_truth),
            predictions=predictions,
            failures=failures,
            total_calls=self.judge.total_api_calls,
            total_cost=self.judge.total_cost,
        )

        logger.info(f"Evaluation complete: accuracy={result.accuracy:.1f}%, failures={len(failures)}")
        return result

    def get_prompts(self) -> tuple[str, str]:
        """Get the current system and user prompts from the judge config."""
        data = self.judge_config.get("data", {})
        return data.get("system", ""), data.get("user", "")


async def main():
    """CLI entry point for evaluation."""
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate a judge on data")
    parser.add_argument("--judge", type=Path, default=Path("config/agents/judge.yml"))
    parser.add_argument("--data", type=Path, default=Path("data/evaluation_set.json"))

    args = parser.parse_args()

    evaluator = JudgeEvaluator(judge_config_path=args.judge)
    examples = load_json(args.data)

    result = await evaluator.evaluate_dataset(examples)

    logger.info("Evaluation Results:")
    logger.info(f"  Accuracy: {result.accuracy:.1f}%")
    logger.info(f"  Balanced Accuracy: {result.balanced_accuracy:.1f}%")
    logger.info(f"  False Positive Rate: {result.false_positive_rate:.1f}%")
    logger.info(f"  False Negative Rate: {result.false_negative_rate:.1f}%")
    logger.info(f"  Calibration Error: {result.calibration_error:.3f}")
    logger.info(f"  Failures: {len(result.failures)}")
    logger.info(f"  API Calls: {result.total_calls}")
    logger.info(f"  Estimated Cost: ${result.total_cost:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
