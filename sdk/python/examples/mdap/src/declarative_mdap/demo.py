"""
Demo script for Declarative MDAP with Tower of Hanoi.

Usage:
    python -m declarative_mdap.demo
    # or via run.sh:
    ./run.sh
"""

import asyncio
import logging
import os
from pathlib import Path

from flatagents import DeclarativeAgent
from .mdap import MDAPOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run():
    """Run the Hanoi demo with MDAP."""
    print("=" * 60)
    print("Declarative MDAP - Tower of Hanoi Demo")
    print("=" * 60)

    # Check for API key
    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("CEREBRAS_API_KEY"):
        print("WARNING: No API key found (OPENAI_API_KEY, CEREBRAS_API_KEY).")
        print("Execution will likely fail.")

    # Load agent from YAML
    config_path = Path(__file__).parent.parent.parent / 'config' / 'hanoi.yml'
    print(f"\nLoading agent from: {config_path}")

    agent = DeclarativeAgent(config_file=str(config_path))
    print(f"Agent: {agent.agent_name}")
    print(f"Model: {agent.model}")

    # Create MDAP orchestrator
    orchestrator = MDAPOrchestrator(agent)

    print(f"\nMDAP Config:")
    print(f"  k_margin: {orchestrator.config.k_margin}")
    print(f"  max_candidates: {orchestrator.config.max_candidates}")
    print(f"  max_steps: {orchestrator.config.max_steps}")

    # Get problem settings from metadata
    hanoi_config = agent.metadata.get('hanoi', {})
    initial_pegs = hanoi_config.get('initial_pegs', [[4, 3, 2, 1], [], []])
    goal_pegs = hanoi_config.get('goal_pegs', [[], [4, 3, 2, 1], []])

    # Initialize state
    pegs = [list(p) for p in initial_pegs]
    previous_move = None
    move_count = 0

    print(f"\nInitial state: {pegs}")
    print(f"Goal: {goal_pegs}")
    print("\n" + "-" * 60)
    print("Starting MDAP execution...\n")

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
    print("\n" + "-" * 60)
    print("Execution Complete!")
    print("-" * 60)

    print("\nExecution trace:")
    for i, state in enumerate(trace):
        print(f"  Step {i}: {state['pegs']}")

    final_pegs = trace[-1]['pegs']
    solved = final_pegs == goal_pegs

    print(f"\nFinal state: {final_pegs}")
    print(f"Solved: {solved}")
    print(f"Total moves: {move_count}")

    print("\n" + "-" * 60)
    print("Statistics")
    print("-" * 60)
    print(f"Total API calls: {orchestrator.total_api_calls}")
    print(f"Total samples: {orchestrator.metrics.total_samples}")
    print(f"Samples per step: {orchestrator.metrics.samples_per_step}")
    if orchestrator.metrics.samples_per_step:
        avg = sum(orchestrator.metrics.samples_per_step) / len(orchestrator.metrics.samples_per_step)
        print(f"Avg samples/step: {avg:.1f}")

    print(f"\nRed-flag metrics:")
    print(f"  Total red-flagged: {orchestrator.metrics.total_red_flags}")
    if orchestrator.metrics.red_flags_by_reason:
        for reason, count in orchestrator.metrics.red_flags_by_reason.items():
            print(f"    {reason}: {count}")

    if solved:
        num_disks = len([d for d in initial_pegs[0] if d > 0])
        optimal_moves = 2 ** num_disks - 1
        print(f"\nOptimal moves for {num_disks} disks: {optimal_moves}")
        if move_count == optimal_moves:
            print("Perfect! Solved in optimal number of moves.")
        else:
            print(f"Solved in {move_count} moves ({move_count - optimal_moves} extra)")
    else:
        print("\nFailed to solve the puzzle.")

    print("\n" + "=" * 60)


def main():
    """Synchronous entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
