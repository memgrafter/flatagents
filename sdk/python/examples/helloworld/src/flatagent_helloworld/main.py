import asyncio
import logging
import os
from pathlib import Path

from flatagents import FlatMachine, LoggingHooks

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


async def run():
    """
    Main function to run the FlatMachine HelloWorld demo.

    The loop and state management is now handled by FlatMachine,
    defined in config/machine.yml.
    """
    print("--- Starting FlatMachine HelloWorld Demo ---")

    # Load the machine from YAML
    config_path = Path(__file__).parent.parent.parent / 'config' / 'machine.yml'
    machine = FlatMachine(
        config_file=str(config_path),
        hooks=LoggingHooks()
    )

    print(f"Machine: {machine.machine_name}")
    print(f"States: {list(machine.states.keys())}\n")

    target = "Hello, World!"
    print(f"Target: '{target}'")
    print(f"Building character by character...\n")

    # Execute the machine - all loop logic is in the config
    result = await machine.execute(input={"target": target})

    print("\n--- Execution Complete ---")
    print(f"Final: '{result.get('result', '')}'")

    if result.get('success'):
        print("Success! The machine built the string correctly.")
    else:
        print("Failure. The machine did not build the string correctly.")

    print("\n--- Execution Statistics ---")
    print(f"Total Cost: ${machine.total_cost:.4f}")
    print(f"Total API Calls: {machine.total_api_calls}")


def main():
    """Synchronous entry point for the script defined in pyproject.toml."""
    asyncio.run(run())


if __name__ == "__main__":
    main()

