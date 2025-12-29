"""
Writer-Critic Demo for FlatAgents.

Demonstrates a simple multi-agent loop where:
1. A writer agent generates marketing taglines
2. A critic agent provides feedback and scores
3. The writer iterates based on feedback until the score is good enough

Usage:
    python -m writer_critic.main
    # or via run.sh:
    ./run.sh
"""

import asyncio
import logging
import os
from pathlib import Path

from flatagents import DeclarativeAgent

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run(product: str = "a CLI tool for AI agents", max_rounds: int = 4, target_score: int = 8):
    """
    Run the writer-critic loop.

    Args:
        product: The product to write taglines for
        max_rounds: Maximum number of revision rounds
        target_score: Stop when score reaches this threshold
    """
    print("=" * 60)
    print("Writer-Critic Demo")
    print("=" * 60)

    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("CEREBRAS_API_KEY"):
        print("WARNING: No API key found (OPENAI_API_KEY, CEREBRAS_API_KEY).")
        print("Execution will likely fail.")

    # Load agents from YAML configs
    config_dir = Path(__file__).parent.parent.parent / 'config'

    writer = DeclarativeAgent(config_file=str(config_dir / 'writer.yml'))
    critic = DeclarativeAgent(config_file=str(config_dir / 'critic.yml'))

    print(f"\nWriter Agent: {writer.agent_name}")
    print(f"Writer Model: {writer.model}")
    print(f"Critic Agent: {critic.agent_name}")
    print(f"Critic Model: {critic.model}")
    print(f"\nProduct: {product}")
    print(f"Target Score: {target_score}/10")
    print(f"Max Rounds: {max_rounds}")
    print("\n" + "-" * 60)

    # Initial draft - no feedback yet
    print("\nGenerating initial tagline...")
    draft = await writer.call(product=product)
    tagline = draft.get('tagline', '')

    print(f"\nInitial tagline: \"{tagline}\"")

    # Iteration loop
    final_score = 0
    for round_num in range(1, max_rounds + 1):
        print(f"\n--- Round {round_num} ---")

        # Get critic feedback
        review = await critic.call(product=product, tagline=tagline)
        score = review.get('score', 0)
        feedback = review.get('feedback', '')

        print(f"Score: {score}/10")
        print(f"Feedback: {feedback}")

        final_score = score

        # Check if we've reached the target
        if score >= target_score:
            print(f"\nTarget score reached!")
            break

        # If not the last round, revise
        if round_num < max_rounds:
            print(f"\nRevising tagline...")
            draft = await writer.call(
                product=product,
                tagline=tagline,
                feedback=feedback
            )
            tagline = draft.get('tagline', tagline)
            print(f"New tagline: \"{tagline}\"")

    # Results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"\nFinal Tagline: \"{tagline}\"")
    print(f"Final Score: {final_score}/10")
    print(f"Rounds: {round_num}")

    print("\n--- Statistics ---")
    total_calls = writer.total_api_calls + critic.total_api_calls
    total_cost = writer.total_cost + critic.total_cost
    print(f"Writer API calls: {writer.total_api_calls}")
    print(f"Critic API calls: {critic.total_api_calls}")
    print(f"Total API calls: {total_calls}")
    print(f"Estimated cost: ${total_cost:.4f}")

    return {
        'tagline': tagline,
        'score': final_score,
        'rounds': round_num,
        'total_calls': total_calls
    }


def main():
    """Synchronous entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
