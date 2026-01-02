"""
Demo script for MDAP with Tower of Hanoi.

Usage:
    python -m mdap.demo
    # or via run.sh:
    ./run.sh
"""

import asyncio
import os
from pathlib import Path

from flatagents import FlatAgent, setup_logging, get_logger
from .mdap import MDAPOrchestrator

# Configure logging
setup_logging(level='INFO')
logger = get_logger(__name__)


async def run():
    """Run the Hanoi demo with MDAP."""
    logger.info("=" * 60)
    logger.info("MDAP - Tower of Hanoi Demo")
    logger.info("=" * 60)

    # Load agent from YAML
    config_path = Path(__file__).parent.parent.parent / 'config' / 'hanoi.yml'
    logger.info(f"Loading agent from: {config_path}")

    agent = FlatAgent(config_file=str(config_path))
    logger.info(f"Agent: {agent.agent_name}")
    logger.info(f"Model: {agent.model}")

    # Create MDAP orchestrator
    orchestrator = MDAPOrchestrator(agent)

    logger.info("MDAP Config:")
    logger.info(f"  k_margin: {orchestrator.config.k_margin}")
    logger.info(f"  max_candidates: {orchestrator.config.max_candidates}")
    logger.info(f"  max_steps: {orchestrator.config.max_steps}")

    # Get problem settings from metadata
    hanoi_config = agent.metadata.get('hanoi', {})
    initial_pegs = hanoi_config.get('initial_pegs', [[4, 3, 2, 1], [], []])
    goal_pegs = hanoi_config.get('goal_pegs', [[], [4, 3, 2, 1], []])

    # Initialize state
    pegs = [list(p) for p in initial_pegs]
    previous_move = None
    move_count = 0

    logger.info(f"Initial state: {pegs}")
    logger.info(f"Goal: {goal_pegs}")
    logger.info("-" * 60)
    logger.info("Starting MDAP execution...")

    # Execute loop
    trace = [{'pegs': [list(p) for p in pegs], 'move_count': 0, 'previous_move': None}]

    for step in range(1, orchestrator.config.max_steps + 1):
        # Check if solved
        if pegs == goal_pegs:
            logger.info(f"Solved after {step - 1} steps")
            break

        logger.info(f"Step {step}: {pegs}")

        # Build input for agent
        input_data = {
            'pegs': pegs,
            'previous_move': previous_move
        }

        # Get winning response via voting
        result, num_samples = await orchestrator.first_to_ahead_by_k(input_data)
        orchestrator.metrics.samples_per_step.append(num_samples)

        if result is None:
            logger.error(f"Step {step} failed - no valid response")
            break

        logger.info(f"Step {step} result: {result} (samples: {num_samples})")

        # Update state
        pegs = result['predicted_state']
        previous_move = result['move']
        move_count += 1

        trace.append({
            'pegs': [list(p) for p in pegs],
            'move_count': move_count,
            'previous_move': previous_move
        })

    # Show results
    logger.info("-" * 60)
    logger.info("Execution Complete!")
    logger.info("-" * 60)

    logger.info("Execution trace:")
    for i, state in enumerate(trace):
        logger.info(f"  Step {i}: {state['pegs']}")

    final_pegs = trace[-1]['pegs']
    solved = final_pegs == goal_pegs

    logger.info(f"Final state: {final_pegs}")
    logger.info(f"Solved: {solved}")
    logger.info(f"Total moves: {move_count}")

    logger.info("-" * 60)
    logger.info("Statistics")
    logger.info("-" * 60)
    logger.info(f"Total API calls: {orchestrator.total_api_calls}")
    logger.info(f"Total samples: {orchestrator.metrics.total_samples}")
    logger.info(f"Samples per step: {orchestrator.metrics.samples_per_step}")
    if orchestrator.metrics.samples_per_step:
        avg = sum(orchestrator.metrics.samples_per_step) / len(orchestrator.metrics.samples_per_step)
        logger.info(f"Avg samples/step: {avg:.1f}")

    logger.info("Red-flag metrics:")
    logger.info(f"  Total red-flagged: {orchestrator.metrics.total_red_flags}")
    if orchestrator.metrics.red_flags_by_reason:
        for reason, count in orchestrator.metrics.red_flags_by_reason.items():
            logger.info(f"    {reason}: {count}")

    if solved:
        num_disks = len([d for d in initial_pegs[0] if d > 0])
        optimal_moves = 2 ** num_disks - 1
        logger.info(f"Optimal moves for {num_disks} disks: {optimal_moves}")
        if move_count == optimal_moves:
            logger.info("Perfect! Solved in optimal number of moves.")
        else:
            logger.info(f"Solved in {move_count} moves ({move_count - optimal_moves} extra)")
    else:
        logger.info("Failed to solve the puzzle.")

    logger.info("=" * 60)


def main():
    """Synchronous entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
