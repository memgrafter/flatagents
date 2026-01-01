"""
Writer-Critic Demo for FlatAgents.

Demonstrates a multi-agent loop orchestrated by FlatMachine:
1. A writer agent generates marketing taglines
2. A critic agent provides feedback and scores
3. Loop continues until score >= target OR max rounds reached

All orchestration is declarative in machine.yml - no Python loop needed.

Usage:
    python -m writer_critic.main
    # or via run.sh:
    ./run.sh
"""

import asyncio
import logging
from pathlib import Path

from flatagents import FlatMachine, LoggingHooks

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run(product: str = "a CLI tool for AI agents", max_rounds: int = 4, target_score: int = 8):
    """
    Run the writer-critic loop via FlatMachine.

    Args:
        product: The product to write taglines for
        max_rounds: Maximum number of revision rounds
        target_score: Stop when score reaches this threshold
    """
    print("=" * 60)
    print("Writer-Critic Demo (FlatMachine)")
    print("=" * 60)

    # Load machine from YAML - all loop logic is declarative
    config_path = Path(__file__).parent.parent.parent / 'config' / 'machine.yml'
    machine = FlatMachine(
        config_file=str(config_path),
        hooks=LoggingHooks()
    )

    print(f"\nMachine: {machine.machine_name}")
    print(f"States: {list(machine.states.keys())}")
    print(f"\nProduct: {product}")
    print(f"Target Score: {target_score}/10")
    print(f"Max Rounds: {max_rounds}")
    print("\n" + "-" * 60)

    # Execute machine - all orchestration is in the YAML
    result = await machine.execute(input={
        "product": product,
        "target_score": target_score,
        "max_rounds": max_rounds
    })

    # Results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"\nFinal Tagline: \"{result.get('tagline', '')}\"")
    print(f"Final Score: {result.get('score', 0)}/10")
    print(f"Rounds: {result.get('rounds', 0)}")

    print("\n--- Statistics ---")
    print(f"Total API calls: {machine.total_api_calls}")
    print(f"Estimated cost: ${machine.total_cost:.4f}")

    return result


def main():
    """Synchronous entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
