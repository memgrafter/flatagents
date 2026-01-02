"""
Data generation using flatagents.

Generates evaluation data with ground truth for training the judge.
"""

import asyncio
import random
from pathlib import Path
from typing import Optional

from flatagents import setup_logging, get_logger
from .utils import load_agent, save_json

# Configure logging
setup_logging(level='INFO')
logger = get_logger(__name__)


class DataGenerator:
    """Generates evaluation data using flatagents."""

    # Error types with their expected verdicts
    ERROR_TYPES = {
        "NONE": "PASS",
        "FACTUAL_ERROR": "FAIL_MAJOR",
        "LOGICAL_FLAW": "FAIL_MAJOR",
        "INCOMPLETE": "FAIL_MINOR",
        "SUBTLE_MISTAKE": "FAIL_MINOR",
        "HALLUCINATION": "FAIL_CRITICAL",
        "MISUNDERSTANDING": "FAIL_MAJOR",
    }

    DOMAINS = ["coding", "reasoning", "factual", "math"]
    DIFFICULTIES = ["easy", "medium", "hard"]

    def __init__(self, config_dir: Path):
        """Initialize with path to agent configs."""
        self.config_dir = config_dir
        self.agents_dir = config_dir / "agents"

        # Load flatagents
        self.task_generator = load_agent(self.agents_dir / "task_generator.yml")
        self.response_generator = load_agent(self.agents_dir / "response_generator.yml")

        logger.info("DataGenerator initialized with flatagents")

    async def generate_task(self, domain: str, difficulty: str) -> dict:
        """Generate a single task using the task generator agent."""
        result = await self.task_generator.call(
            domain=domain,
            difficulty=difficulty,
        )
        return result

    async def generate_response(
        self,
        task: str,
        correct_response: str,
        error_type: str,
    ) -> dict:
        """Generate a response (with or without errors) using the response generator agent."""
        result = await self.response_generator.call(
            task=task,
            correct_response=correct_response,
            error_type=error_type,
        )
        return result

    async def generate_example(
        self,
        domain: Optional[str] = None,
        difficulty: Optional[str] = None,
        error_type: Optional[str] = None,
    ) -> dict:
        """Generate a complete evaluation example."""
        # Random selection if not specified
        domain = domain or random.choice(self.DOMAINS)
        difficulty = difficulty or random.choice(self.DIFFICULTIES)
        error_type = error_type or random.choice(list(self.ERROR_TYPES.keys()))

        logger.info(f"Generating example: domain={domain}, difficulty={difficulty}, error={error_type}")

        # Step 1: Generate task
        task_result = await self.generate_task(domain, difficulty)
        task_output = task_result.output or {}

        # Step 2: Generate response with specified error type
        response_result = await self.generate_response(
            task=task_output.get("task", ""),
            correct_response=task_output.get("correct_response", ""),
            error_type=error_type,
        )
        response_output = response_result.output or {}

        # Combine into evaluation example
        example = {
            "task": task_output.get("task", ""),
            "correct_response": task_output.get("correct_response", ""),
            "evaluation_criteria": task_output.get("evaluation_criteria", ""),
            "key_elements": task_output.get("key_elements", []),
            "agent_response": response_output.get("response", ""),
            "has_error": response_output.get("has_error", False),
            "error_type": error_type,
            "error_description": response_output.get("error_description", ""),
            "expected_verdict": response_output.get("expected_verdict", self.ERROR_TYPES.get(error_type, "PASS")),
            "domain": domain,
            "difficulty": difficulty,
        }

        return example

    async def generate_dataset(
        self,
        num_examples: int = 50,
        correct_ratio: float = 0.3,
    ) -> list[dict]:
        """
        Generate a balanced dataset for evaluation.

        Args:
            num_examples: Total number of examples to generate
            correct_ratio: Proportion of examples that should be correct (no errors)

        Returns:
            List of evaluation examples with ground truth
        """
        logger.info(f"Generating dataset with {num_examples} examples")

        examples = []
        num_correct = int(num_examples * correct_ratio)
        num_errors = num_examples - num_correct

        # Generate correct examples
        for i in range(num_correct):
            logger.info(f"Generating correct example {i+1}/{num_correct}")
            example = await self.generate_example(error_type="NONE")
            examples.append(example)

        # Generate examples with various error types
        error_types = [k for k in self.ERROR_TYPES.keys() if k != "NONE"]
        for i in range(num_errors):
            error_type = error_types[i % len(error_types)]
            logger.info(f"Generating error example {i+1}/{num_errors} ({error_type})")
            example = await self.generate_example(error_type=error_type)
            examples.append(example)

        # Shuffle the dataset
        random.shuffle(examples)

        logger.info(f"Generated {len(examples)} examples")
        return examples

    def save_dataset(self, examples: list[dict], output_path: Path) -> None:
        """Save dataset to JSON file."""
        save_json(examples, output_path)
        logger.info(f"Saved dataset to {output_path}")

    def get_stats(self) -> dict:
        """Get statistics about LLM calls made."""
        return {
            "task_generator_calls": self.task_generator.total_api_calls,
            "task_generator_cost": self.task_generator.total_cost,
            "response_generator_calls": self.response_generator.total_api_calls,
            "response_generator_cost": self.response_generator.total_cost,
        }


async def main():
    """CLI entry point for data generation."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate evaluation data")
    parser.add_argument("--num-examples", type=int, default=50)
    parser.add_argument("--correct-ratio", type=float, default=0.3)
    parser.add_argument("--output", type=Path, default=Path("data/evaluation_set.json"))
    parser.add_argument("--config-dir", type=Path, default=Path("config"))

    args = parser.parse_args()

    generator = DataGenerator(args.config_dir)
    examples = await generator.generate_dataset(
        num_examples=args.num_examples,
        correct_ratio=args.correct_ratio,
    )
    generator.save_dataset(examples, args.output)

    logger.info(f"Generated {len(examples)} examples")
    logger.info(f"Stats: {generator.get_stats()}")


if __name__ == "__main__":
    asyncio.run(main())
