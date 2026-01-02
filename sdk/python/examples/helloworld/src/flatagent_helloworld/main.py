import asyncio
import os
from pathlib import Path

from flatagents import FlatMachine, LoggingHooks, setup_logging, get_logger

# Configure logging for the entire application
setup_logging(level='INFO')
logger = get_logger(__name__)


async def run():
    """
    Main function to run the FlatMachine HelloWorld demo.

    The loop and state management is now handled by FlatMachine,
    defined in config/machine.yml.
    """
    logger.info("--- Starting FlatMachine HelloWorld Demo ---")

    # Load the machine from YAML
    config_path = Path(__file__).parent.parent.parent / 'config' / 'machine.yml'
    machine = FlatMachine(
        config_file=str(config_path),
        hooks=LoggingHooks()
    )

    logger.info(f"Machine: {machine.machine_name}")
    logger.info(f"States: {list(machine.states.keys())}")

    target = "Hello, World!"
    logger.info(f"Target: '{target}'")
    logger.info("Building character by character...")

    # Execute the machine - all loop logic is in the config
    result = await machine.execute(input={"target": target})

    logger.info("--- Execution Complete ---")
    logger.info(f"Final: '{result.get('result', '')}'")

    if result.get('success'):
        logger.info("Success! The machine built the string correctly.")
    else:
        logger.warning("Failure. The machine did not build the string correctly.")

    logger.info("--- Execution Statistics ---")
    logger.info(f"Total Cost: ${machine.total_cost:.4f}")
    logger.info(f"Total API Calls: {machine.total_api_calls}")


def main():
    """Synchronous entry point for the script defined in pyproject.toml."""
    asyncio.run(run())


if __name__ == "__main__":
    main()

