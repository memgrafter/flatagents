"""
MDAP Demo using FlatMachine.

Now uses declarative execution types - no Python loop required.

Usage:
    python -m mdap.demo_machine
"""

import asyncio
from pathlib import Path

from flatagents import FlatMachine, FlatAgent, MDAPVotingExecution, setup_logging, get_logger

# Configure logging
setup_logging(level='INFO')
logger = get_logger(__name__)


async def run():
    """Run the Hanoi demo with FlatMachine + MDAP voting execution type."""
    logger.info("=" * 60)
    logger.info("MDAP - Tower of Hanoi Demo (FlatMachine)")
    logger.info("=" * 60)

    # Load machine config
    config_path = Path(__file__).parent.parent.parent / 'config' / 'machine.yml'
    logger.info(f"Loading machine from: {config_path}")

    # Load machine - execution types are declared in YAML, no manual wiring needed
    machine = FlatMachine(config_file=str(config_path))

    logger.info(f"Machine: {machine.machine_name}")
    logger.info(f"States: {list(machine.states.keys())}")

    # Get problem settings from agent metadata
    agent_path = Path(__file__).parent.parent.parent / 'config' / 'hanoi.yml'
    agent = FlatAgent(config_file=str(agent_path))
    hanoi_config = agent.metadata.get('hanoi', {})
    initial_pegs = hanoi_config.get('initial_pegs', [[3, 2, 1], [], []])
    goal_pegs = hanoi_config.get('goal_pegs', [[], [3, 2, 1], []])

    # Show MDAP config from the state's execution section
    solve_step = machine.states.get('solve_step', {})
    execution_config = solve_step.get('execution', {})
    logger.info("Execution Config (from machine.yml):")
    logger.info(f"  type: {execution_config.get('type', 'default')}")
    logger.info(f"  k_margin: {execution_config.get('k_margin', 'N/A')}")
    logger.info(f"  max_candidates: {execution_config.get('max_candidates', 'N/A')}")

    logger.info(f"Initial state: {initial_pegs}")
    logger.info(f"Goal: {goal_pegs}")
    logger.info("-" * 60)
    logger.info("Starting FlatMachine execution...")
    logger.info("-" * 60)

    # Execute machine - all orchestration is YAML-driven
    result = await machine.execute(
        input={
            'initial_pegs': initial_pegs,
            'goal_pegs': goal_pegs
        }
    )

    # Results
    logger.info("-" * 60)
    logger.info("Execution Complete!")
    logger.info("-" * 60)

    logger.info(f"Final state: {result.get('pegs')}")
    logger.info(f"Solved: {result.get('solved')}")
    logger.info(f"Total steps: {result.get('steps')}")

    logger.info(f"Total API calls: {machine.total_api_calls}")
    logger.info("=" * 60)


def main():
    """Synchronous entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
