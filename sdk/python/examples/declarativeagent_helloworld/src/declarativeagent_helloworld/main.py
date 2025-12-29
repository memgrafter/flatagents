import asyncio
import logging
import os
from pathlib import Path

from flatagents import DeclarativeAgent

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


async def run():
    """
    Main function to run the DeclarativeAgent HelloWorld demo.

    In v0.4.0, the agent is a single LLM call. The loop is managed here.
    """
    print("--- Starting DeclarativeAgent HelloWorld Demo ---")

    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("CEREBRAS_API_KEY"):
        print("WARNING: No API key found in environment (OPENAI_API_KEY, CEREBRAS_API_KEY). "
              "Execution will likely fail.")

    # Load the agent from YAML
    config_path = Path(__file__).parent.parent.parent / 'config' / 'agent.yml'
    agent = DeclarativeAgent(config_file=str(config_path))

    print(f"Agent: {agent.agent_name}")
    print(f"Model: {agent.model}\n")

    # Initialize state (workflow manages this in v0.4.0)
    current = ""
    target = "Hello, World!"
    max_steps = 50

    print(f"Target: '{target}'")
    print(f"Building character by character...\n")

    for step in range(max_steps):
        if current == target:
            break

        # Call agent with input
        result = await agent.call(current=current, target=target)

        # Extract next character
        next_char = result.get('next_char', '')
        if not next_char:
            print(f"  Step {step + 1}: No character returned, stopping")
            break

        current += next_char
        print(f"  Step {step + 1}: '{next_char}' -> '{current}'")

    print("\n--- Execution Complete ---")
    print(f"Final: '{current}'")

    if current == target:
        print("Success! The agent built the string correctly.")
    else:
        print("Failure. The agent did not build the string correctly.")

    print("\n--- Execution Statistics ---")
    print(f"Total Cost: ${agent.total_cost:.4f}")
    print(f"Total API Calls: {agent.total_api_calls}")


def main():
    """Synchronous entry point for the script defined in pyproject.toml."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
