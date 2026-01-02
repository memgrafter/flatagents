"""
Human-in-the-Loop Demo for FlatAgents.

Demonstrates a workflow where an AI generates content,
then pauses for human approval before completing.
The human can either approve the draft or provide feedback
for the AI to revise.

Usage:
    python -m human_in_loop.main
    # or via run.sh:
    ./run.sh
"""

import argparse
import asyncio
import logging
from pathlib import Path

from flatagents import FlatMachine
from .hooks import HumanInLoopHooks

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run(topic: str = "the benefits of daily exercise", max_revisions: int = 3):
    """
    Run the human-in-the-loop workflow via FlatMachine.

    Args:
        topic: The topic to write about
        max_revisions: Maximum number of revision rounds
    """
    print("=" * 60)
    print("Human-in-the-Loop Demo (FlatMachine)")
    print("=" * 60)

    # Load machine from YAML
    config_path = Path(__file__).parent.parent.parent / 'config' / 'machine.yml'
    machine = FlatMachine(
        config_file=str(config_path),
        hooks=HumanInLoopHooks()
    )

    print(f"\nMachine: {machine.machine_name}")
    print(f"States: {list(machine.states.keys())}")
    print(f"\nTopic: {topic}")
    print(f"Max Revisions: {max_revisions}")
    print("\n" + "-" * 60)

    # Execute machine
    result = await machine.execute(input={
        "topic": topic,
        "max_revisions": max_revisions
    })

    # Results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"\nStatus: {result.get('status', 'unknown')}")
    print(f"Revisions: {result.get('revisions', 0)}")
    print(f"\nFinal Content:")
    print("-" * 40)
    print(result.get('content', ''))
    print("-" * 40)

    print("\n--- Statistics ---")
    print(f"Total API calls: {machine.total_api_calls}")
    print(f"Estimated cost: ${machine.total_cost:.4f}")

    return result


def main():
    """Synchronous entry point with CLI args."""
    parser = argparse.ArgumentParser(
        description="Human-in-the-loop content generation"
    )
    parser.add_argument(
        "--topic",
        default="the benefits of daily exercise",
        help="Topic to write about"
    )
    parser.add_argument(
        "--max-revisions",
        type=int,
        default=3,
        help="Maximum number of revisions (default: 3)"
    )
    args = parser.parse_args()
    
    asyncio.run(run(topic=args.topic, max_revisions=args.max_revisions))


if __name__ == "__main__":
    main()
