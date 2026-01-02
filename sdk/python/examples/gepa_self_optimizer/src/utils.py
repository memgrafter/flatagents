"""
Utility functions for the GEPA self-optimizer.
"""

import json
from pathlib import Path
from typing import Any

import yaml

from flatagents import FlatAgent, get_logger


def load_yaml(path: Path) -> dict:
    """Load a YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


def save_yaml(data: dict, path: Path) -> None:
    """Save data to a YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def load_json(path: Path) -> Any:
    """Load a JSON file."""
    with open(path) as f:
        return json.load(f)


def save_json(data: Any, path: Path) -> None:
    """Save data to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_agent(config_path: Path) -> FlatAgent:
    """Load a flatagent from a config file."""
    return FlatAgent(config_file=str(config_path))


def create_agent_from_dict(config: dict) -> FlatAgent:
    """Create a flatagent from a config dictionary."""
    return FlatAgent(config_dict=config)


def update_agent_prompts(
    original_config: dict,
    new_system_prompt: str,
    new_user_prompt: str,
) -> dict:
    """Create a new agent config with updated prompts."""
    config = json.loads(json.dumps(original_config))  # Deep copy
    config["data"]["system"] = new_system_prompt
    config["data"]["user"] = new_user_prompt
    return config


def calculate_accuracy(predictions: list[dict], ground_truth: list[dict]) -> float:
    """Calculate accuracy of predictions vs ground truth."""
    if not predictions or not ground_truth:
        return 0.0

    correct = sum(
        1 for p, g in zip(predictions, ground_truth)
        if p.get("verdict") == g.get("expected_verdict")
    )
    return correct / len(predictions) * 100


def calculate_false_positive_rate(predictions: list[dict], ground_truth: list[dict]) -> float:
    """Calculate false positive rate (approved when should have failed)."""
    false_positives = 0
    actual_negatives = 0

    for p, g in zip(predictions, ground_truth):
        expected = g.get("expected_verdict", "PASS")
        predicted = p.get("verdict", "PASS")

        # Actual negative: expected to fail
        if expected != "PASS":
            actual_negatives += 1
            # False positive: we said PASS when we shouldn't have
            if predicted == "PASS":
                false_positives += 1

    if actual_negatives == 0:
        return 0.0
    return false_positives / actual_negatives * 100


def calculate_false_negative_rate(predictions: list[dict], ground_truth: list[dict]) -> float:
    """Calculate false negative rate (rejected when should have passed)."""
    false_negatives = 0
    actual_positives = 0

    for p, g in zip(predictions, ground_truth):
        expected = g.get("expected_verdict", "PASS")
        predicted = p.get("verdict", "PASS")

        # Actual positive: expected to pass
        if expected == "PASS":
            actual_positives += 1
            # False negative: we said FAIL when we shouldn't have
            if predicted != "PASS":
                false_negatives += 1

    if actual_positives == 0:
        return 0.0
    return false_negatives / actual_positives * 100


def calculate_calibration_error(predictions: list[dict], ground_truth: list[dict]) -> float:
    """Calculate mean absolute calibration error."""
    errors = []

    for p, g in zip(predictions, ground_truth):
        expected = g.get("expected_verdict", "PASS")
        predicted = p.get("verdict", "PASS")
        confidence = p.get("confidence", 0.5)

        # Actual correctness: 1 if prediction matches, 0 otherwise
        actual_correct = 1.0 if predicted == expected else 0.0

        # Calibration error: difference between confidence and actual correctness
        errors.append(abs(confidence - actual_correct))

    if not errors:
        return 0.0
    return sum(errors) / len(errors)
