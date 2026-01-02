"""
Calibration for MDAP.

Provides a Calibrator class to estimate per-step success rates and calculate
optimal k values based on the MAKER paper formulas.
"""

import asyncio
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from flatagents import setup_logging, get_logger
from .mdap import MDAPOrchestrator, MDAPConfig

# Configure logging
setup_logging(level='INFO')
logger = get_logger(__name__)


@dataclass
class CalibrationResult:
    """Results from a calibration run."""
    success_rate: float
    total_samples: int
    correct_samples: int
    k_min_90: int
    k_min_95: int
    k_min_99: int
    expected_samples_per_step: float
    estimated_cost: float


class Calibrator(ABC):
    """
    Base calibrator for MDAP success rate estimation.

    Subclass and implement:
    - generate_sample_inputs(): Create inputs to test
    - get_optimal_result(input_data): Return the correct result for an input
    - compare_results(result, optimal): Check if result matches optimal
    """

    def __init__(
        self,
        orchestrator: MDAPOrchestrator,
        num_steps: int,
        cost_per_call: float = 0.001
    ):
        self.orchestrator = orchestrator
        self.num_steps = num_steps
        self.cost_per_call = cost_per_call

    @abstractmethod
    def generate_sample_inputs(self, max_samples: Optional[int] = None) -> List[Dict[str, Any]]:
        """Generate sample inputs for calibration."""
        pass

    @abstractmethod
    def get_optimal_result(self, input_data: Dict[str, Any]) -> Any:
        """Return the optimal/correct result for a given input."""
        pass

    def compare_results(self, result: Any, optimal: Any) -> bool:
        """Compare if result matches optimal. Override for custom comparison."""
        return result == optimal

    async def estimate_success_rate(
        self,
        sample_inputs: Optional[List[Dict[str, Any]]] = None
    ) -> float:
        """
        Estimate per-step success rate by comparing to optimal.

        Args:
            sample_inputs: Inputs to test (generates if None)

        Returns:
            Success rate (0.0 to 1.0)
        """
        if sample_inputs is None:
            sample_inputs = self.generate_sample_inputs()

        if not sample_inputs:
            return 0.0

        correct = 0
        total = len(sample_inputs)

        for i, input_data in enumerate(sample_inputs):
            logger.info(f"Calibration sample {i+1}/{total}")

            result, _ = await self.orchestrator.first_to_ahead_by_k(input_data)
            if result is None:
                continue

            optimal = self.get_optimal_result(input_data)

            if self.compare_results(result, optimal):
                correct += 1
                logger.debug(f"Sample {i+1}: correct")
            else:
                logger.debug(f"Sample {i+1}: incorrect (got {result}, expected {optimal})")

        rate = correct / total if total > 0 else 0.0
        logger.info(f"Per-step success rate: {rate:.2%} ({correct}/{total})")
        return rate

    @staticmethod
    def calculate_k_min(
        p: float,
        n: int,
        target_reliability: float = 0.99
    ) -> int:
        """
        Calculate minimum k for target reliability.

        Uses binomial probability from MAKER paper.
        """
        if p >= 1.0:
            return 1
        if p <= 0.5:
            logger.warning(f"p={p} <= 0.5, voting cannot help")
            return 100

        for k in range(1, 100):
            prob = sum(
                math.comb(2*k-1, i) * (p**i) * ((1-p)**(2*k-1-i))
                for i in range(k, 2*k)
            )
            step_reliability = prob ** n
            if step_reliability >= target_reliability:
                return k

        return 100

    @staticmethod
    def calculate_expected_samples(k: int, p: float) -> float:
        """Calculate expected samples for first-to-ahead-by-k."""
        if p >= 1.0:
            return float(k)
        if p <= 0.0:
            return float('inf')
        return k / p

    def estimate_total_cost(self, k: int, p: float) -> float:
        """Estimate total cost for solving with MDAP."""
        expected_samples = self.calculate_expected_samples(k, p)
        return expected_samples * self.num_steps * self.cost_per_call

    async def run(self, max_samples: Optional[int] = None) -> CalibrationResult:
        """Run full calibration and return results."""
        sample_inputs = self.generate_sample_inputs(max_samples)
        success_rate = await self.estimate_success_rate(sample_inputs)

        k_min_90 = self.calculate_k_min(success_rate, self.num_steps, 0.90)
        k_min_95 = self.calculate_k_min(success_rate, self.num_steps, 0.95)
        k_min_99 = self.calculate_k_min(success_rate, self.num_steps, 0.99)

        expected_samples = self.calculate_expected_samples(3, success_rate)
        estimated_cost = self.estimate_total_cost(3, success_rate)

        return CalibrationResult(
            success_rate=success_rate,
            total_samples=len(sample_inputs),
            correct_samples=int(success_rate * len(sample_inputs)),
            k_min_90=k_min_90,
            k_min_95=k_min_95,
            k_min_99=k_min_99,
            expected_samples_per_step=expected_samples,
            estimated_cost=estimated_cost
        )


class HanoiCalibrator(Calibrator):
    """
    Calibrator for Tower of Hanoi problem.

    Note: Only even disk counts are supported per the MAKER paper.
    """

    def __init__(
        self,
        orchestrator: MDAPOrchestrator,
        num_disks: int = 4,
        cost_per_call: float = 0.001
    ):
        if num_disks % 2 != 0:
            raise ValueError(
                f"Only even disk counts supported (got {num_disks}). "
                "The clockwise algorithm targets peg 1 for even, peg 2 for odd."
            )

        num_steps = 2 ** num_disks - 1
        super().__init__(orchestrator, num_steps, cost_per_call)
        self.num_disks = num_disks

    def generate_sample_inputs(self, max_samples: Optional[int] = None) -> List[Dict[str, Any]]:
        """Generate sample inputs by simulating optimal solution."""
        import random

        all_inputs = []
        n = self.num_disks

        # Start with initial state
        pegs = [list(range(n, 0, -1)), [], []]
        previous_move = None

        # Add initial input
        all_inputs.append({
            'pegs': [list(p) for p in pegs],
            'previous_move': previous_move
        })

        # Simulate optimal solution and collect inputs
        optimal_moves = 2 ** n - 1
        for _ in range(optimal_moves):
            result = self.get_optimal_result({
                'pegs': pegs,
                'previous_move': previous_move
            })

            if result is None:
                break

            pegs = result['predicted_state']
            previous_move = result['move']

            # Add input (except for final solved state)
            if _ < optimal_moves - 1:
                all_inputs.append({
                    'pegs': [list(p) for p in pegs],
                    'previous_move': previous_move
                })

        # Sample if too many inputs
        if max_samples and len(all_inputs) > max_samples:
            sampled = [all_inputs[0]]
            middle = all_inputs[1:-1]
            random.shuffle(middle)
            sampled.extend(middle[:max_samples - 2])
            sampled.append(all_inputs[-1])
            return sampled

        return all_inputs

    def get_optimal_result(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate optimal next move for Tower of Hanoi."""
        pegs = input_data['pegs']
        previous_move = input_data.get('previous_move')

        # Find where disk 1 is
        disk1_peg = None
        for i, peg in enumerate(pegs):
            if peg and peg[-1] == 1:
                disk1_peg = i
                break

        if previous_move is None or previous_move[0] != 1:
            # Move disk 1 clockwise
            if disk1_peg is not None:
                to_peg = (disk1_peg + 1) % 3
                new_pegs = [list(p) for p in pegs]
                new_pegs[disk1_peg].pop()
                new_pegs[to_peg].append(1)
                return {
                    'move': [1, disk1_peg, to_peg],
                    'predicted_state': new_pegs
                }
        else:
            # Make the only legal move not involving disk 1
            other_pegs = [i for i, peg in enumerate(pegs) if not peg or peg[-1] != 1]

            if len(other_pegs) >= 2:
                peg_a, peg_b = other_pegs[0], other_pegs[1]
                top_a = pegs[peg_a][-1] if pegs[peg_a] else float('inf')
                top_b = pegs[peg_b][-1] if pegs[peg_b] else float('inf')

                if top_a < top_b:
                    from_peg, to_peg, disk = peg_a, peg_b, top_a
                else:
                    from_peg, to_peg, disk = peg_b, peg_a, top_b

                if disk != float('inf'):
                    new_pegs = [list(p) for p in pegs]
                    new_pegs[from_peg].pop()
                    new_pegs[to_peg].append(int(disk))
                    return {
                        'move': [int(disk), from_peg, to_peg],
                        'predicted_state': new_pegs
                    }

        return None

    def compare_results(self, result: Any, optimal: Any) -> bool:
        """Compare moves (ignore predicted_state differences)."""
        if result is None or optimal is None:
            return False
        return result.get('move') == optimal.get('move')


async def run_hanoi_calibration(
    config_path: str,
    num_disks: int = 4,
    max_samples: Optional[int] = None
) -> CalibrationResult:
    """Convenience function to run Hanoi calibration."""
    from flatagents import FlatAgent

    agent = FlatAgent(config_file=config_path)

    # Use k=1 for raw success rate (no voting amplification)
    calibration_config = MDAPConfig(k_margin=1, max_candidates=1)
    orchestrator = MDAPOrchestrator(agent, calibration_config)

    calibrator = HanoiCalibrator(orchestrator, num_disks=num_disks)
    return await calibrator.run(max_samples=max_samples)


def main():
    """CLI entry point for calibration."""
    import argparse
    import os
    from pathlib import Path

    parser = argparse.ArgumentParser(description="MDAP Calibration for Tower of Hanoi")
    parser.add_argument(
        "--disks", "-d",
        type=int,
        default=4,
        help="Number of disks (default: 4, must be even)"
    )
    parser.add_argument(
        "--samples", "-s",
        type=int,
        default=20,
        help="Max states to test (default: 20)"
    )
    args = parser.parse_args()

    num_disks = args.disks
    max_samples = args.samples
    optimal_moves = 2 ** num_disks - 1

    logger.info("=" * 60)
    logger.info(f"MDAP Calibration - Tower of Hanoi ({num_disks} disks)")
    logger.info("=" * 60)

    config_path = Path(__file__).parent.parent.parent / 'config' / 'hanoi.yml'
    logger.info(f"Config: {config_path}")
    logger.info(f"Optimal solution: {optimal_moves} moves")
    logger.info(f"Max samples: {max_samples}")

    result = asyncio.run(run_hanoi_calibration(
        str(config_path),
        num_disks=num_disks,
        max_samples=max_samples
    ))

    logger.info("=" * 60)
    logger.info("Calibration Results")
    logger.info("=" * 60)
    logger.info(f"Disks: {num_disks}")
    logger.info(f"Per-step success rate: {result.success_rate:.2%}")
    logger.info(f"Samples tested: {result.total_samples}")
    logger.info(f"Correct: {result.correct_samples}")
    logger.info(f"k_min for 90% reliability: {result.k_min_90}")
    logger.info(f"k_min for 95% reliability: {result.k_min_95}")
    logger.info(f"k_min for 99% reliability: {result.k_min_99}")
    logger.info(f"Expected samples/step (k=3): {result.expected_samples_per_step:.1f}")
    logger.info(f"Estimated cost (k=3): ${result.estimated_cost:.4f}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
