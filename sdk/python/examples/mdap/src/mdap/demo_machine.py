"""
MDAP Demo using FlatMachine.

Now uses declarative execution types - no Python loop required.

Usage:
    python -m mdap.demo_machine
"""

import asyncio
import logging
from pathlib import Path

from flatagents import FlatMachine, FlatAgent, MDAPVotingExecution

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run():
    """Run the Hanoi demo with FlatMachine + MDAP voting execution type."""
    print("=" * 60)
    print("MDAP - Tower of Hanoi Demo (FlatMachine)")
    print("=" * 60)

    # Load machine config
    config_path = Path(__file__).parent.parent.parent / 'config' / 'machine.yml'
    print(f"\nLoading machine from: {config_path}")

    # Load machine - execution types are declared in YAML, no manual wiring needed
    machine = FlatMachine(config_file=str(config_path))

    print(f"Machine: {machine.machine_name}")
    print(f"States: {list(machine.states.keys())}")

    # Get problem settings from agent metadata
    agent_path = Path(__file__).parent.parent.parent / 'config' / 'hanoi.yml'
    agent = FlatAgent(config_file=str(agent_path))
    hanoi_config = agent.metadata.get('hanoi', {})
    initial_pegs = hanoi_config.get('initial_pegs', [[3, 2, 1], [], []])
    goal_pegs = hanoi_config.get('goal_pegs', [[], [3, 2, 1], []])

    # Show MDAP config from the state's execution section
    solve_step = machine.states.get('solve_step', {})
    execution_config = solve_step.get('execution', {})
    print(f"\nExecution Config (from machine.yml):")
    print(f"  type: {execution_config.get('type', 'default')}")
    print(f"  k_margin: {execution_config.get('k_margin', 'N/A')}")
    print(f"  max_candidates: {execution_config.get('max_candidates', 'N/A')}")

    print(f"\nInitial state: {initial_pegs}")
    print(f"Goal: {goal_pegs}")
    print("\n" + "-" * 60)
    print("Starting FlatMachine execution...")
    print("-" * 60 + "\n")

    # Execute machine - all orchestration is YAML-driven
    result = await machine.execute(
        input={
            'initial_pegs': initial_pegs,
            'goal_pegs': goal_pegs
        }
    )

    # Results
    print("\n" + "-" * 60)
    print("Execution Complete!")
    print("-" * 60)

    print(f"\nFinal state: {result.get('pegs')}")
    print(f"Solved: {result.get('solved')}")
    print(f"Total steps: {result.get('steps')}")

    print(f"\nTotal API calls: {machine.total_api_calls}")

    print("\n" + "=" * 60)


def main():
    """Synchronous entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
