"""Error handling demo with cleanup agent."""

import asyncio
from pathlib import Path
from flatagents import FlatMachine, LoggingHooks


async def run():
    config_path = Path(__file__).parent.parent.parent / 'config' / 'machine.yml'
    machine = FlatMachine(config_file=str(config_path), hooks=LoggingHooks())

    print(f"Machine: {machine.machine_name}")
    print(f"States: {list(machine.states.keys())}\n")

    result = await machine.execute(input={"task": "Analyze market trends"})

    print(f"\nResult:")
    print(f"  Success: {result.get('success')}")
    if result.get('success'):
        print(f"  Result: {result.get('result')}")
    else:
        print(f"  Summary: {result.get('summary')}")
        print(f"  Error: {result.get('error_type')}")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
