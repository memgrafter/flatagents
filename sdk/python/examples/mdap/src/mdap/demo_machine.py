"""
MDAP Demo using FlatMachine.

Usage:
    python -m mdap.demo_machine
"""

import asyncio
import logging
import os
from pathlib import Path

from flatagents import FlatMachine, FlatAgent
from .hooks import MDAPHooks

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run():
    """Run the Hanoi demo with FlatMachine + MDAP hooks."""
    print("=" * 60)
    print("MDAP - Tower of Hanoi Demo (FlatMachine)")
    print("=" * 60)

    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("CEREBRAS_API_KEY"):
        print("WARNING: No API key found (OPENAI_API_KEY, CEREBRAS_API_KEY).")
        print("Execution will likely fail.")

    # Load machine config
    config_path = Path(__file__).parent.parent.parent / 'config' / 'machine.yml'
    print(f"\nLoading machine from: {config_path}")

    # Create MDAP hooks
    mdap_hooks = MDAPHooks()

    # Load machine with hooks
    machine = FlatMachine(
        config_file=str(config_path),
        hooks=mdap_hooks
    )

    print(f"Machine: {machine.machine_name}")
    print(f"States: {list(machine.states.keys())}")

    # Get problem settings from agent metadata
    agent_path = Path(__file__).parent.parent.parent / 'config' / 'hanoi.yml'
    agent = FlatAgent(config_file=str(agent_path))
    hanoi_config = agent.metadata.get('hanoi', {})
    initial_pegs = hanoi_config.get('initial_pegs', [[3, 2, 1], [], []])
    goal_pegs = hanoi_config.get('goal_pegs', [[], [3, 2, 1], []])

    # Configure hooks from agent (for parsing/validation)
    mdap_hooks.configure_from_agent(agent)

    print(f"\nMDAP Config:")
    print(f"  k_margin: {mdap_hooks.config.k_margin}")
    print(f"  max_candidates: {mdap_hooks.config.max_candidates}")

    print(f"\nInitial state: {initial_pegs}")
    print(f"Goal: {goal_pegs}")
    print("\n" + "-" * 60)
    print("Starting FlatMachine execution...")
    print("-" * 60 + "\n")

    # Execute machine
    # NOTE: The current FlatMachine uses single agent calls.
    # For full MDAP voting, we'd need to extend FlatMachine or
    # use the voting_call hook directly. Here's a hybrid approach:

    # Run step-by-step with voting
    context = {
        'pegs': [list(p) for p in initial_pegs],
        'goal': goal_pegs,
        'previous_move': None,
        'step': 0,
        'solved': False
    }

    trace = [{'pegs': [list(p) for p in context['pegs']], 'step': 0}]

    while context['step'] < 20:
        # Check if solved
        if context['pegs'] == context['goal']:
            context['solved'] = True
            break

        logger.info(f"Step {context['step'] + 1}: {context['pegs']}")

        # Use voting call
        input_data = {
            'pegs': context['pegs'],
            'previous_move': context['previous_move']
        }

        result = await mdap_hooks.voting_call(agent, input_data)

        if result is None:
            logger.error("No valid response from voting")
            break

        # Update context
        context['pegs'] = result.get('predicted_state', context['pegs'])
        context['previous_move'] = result.get('move')
        context['step'] += 1

        trace.append({
            'pegs': [list(p) for p in context['pegs']],
            'step': context['step'],
            'move': context['previous_move']
        })

    # Results
    print("\n" + "-" * 60)
    print("Execution Complete!")
    print("-" * 60)

    print("\nExecution trace:")
    for state in trace:
        print(f"  Step {state['step']}: {state['pegs']}")

    print(f"\nFinal state: {context['pegs']}")
    print(f"Solved: {context['solved']}")
    print(f"Total steps: {context['step']}")

    print("\n" + "-" * 60)
    print("MDAP Statistics")
    print("-" * 60)
    metrics = mdap_hooks.get_metrics()
    print(f"Total samples: {metrics['total_samples']}")
    print(f"Samples per step: {metrics['samples_per_step']}")
    if metrics['samples_per_step']:
        avg = sum(metrics['samples_per_step']) / len(metrics['samples_per_step'])
        print(f"Avg samples/step: {avg:.1f}")

    print(f"\nRed-flag metrics:")
    print(f"  Total red-flagged: {metrics['total_red_flags']}")
    for reason, count in metrics.get('red_flags_by_reason', {}).items():
        print(f"    {reason}: {count}")

    print(f"\nTotal API calls: {agent.total_api_calls}")

    print("\n" + "=" * 60)


def main():
    """Synchronous entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
