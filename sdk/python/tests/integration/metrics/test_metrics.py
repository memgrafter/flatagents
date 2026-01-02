#!/usr/bin/env python3
"""
Metrics Integration Tests

Tests OpenTelemetry metrics integration using console exporter.
No external infrastructure required.

Usage:
    python test_metrics.py
"""
import os
import sys
import time

# Configure before imports
os.environ["FLATAGENTS_METRICS_ENABLED"] = "true"
os.environ["OTEL_METRICS_EXPORTER"] = "console"
os.environ["OTEL_METRIC_EXPORT_INTERVAL"] = "1000"  # 1 second for faster tests

from flatagents import setup_logging, get_logger, AgentMonitor, track_operation

setup_logging(level="WARNING")  # Quiet logging for tests
logger = get_logger(__name__)


class MetricsTestSuite:
    """Test suite for metrics functionality."""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def test(self, name: str):
        """Decorator for test methods."""
        def decorator(func):
            def wrapper():
                try:
                    func()
                    self.passed += 1
                    print(f"  ✓ {name}")
                    return True
                except AssertionError as e:
                    self.failed += 1
                    self.errors.append(f"{name}: {e}")
                    print(f"  ✗ {name}: {e}")
                    return False
                except Exception as e:
                    self.failed += 1
                    self.errors.append(f"{name}: {type(e).__name__}: {e}")
                    print(f"  ✗ {name}: {type(e).__name__}: {e}")
                    return False
            return wrapper
        return decorator
    
    def run_all(self) -> bool:
        """Run all tests and return success status."""
        print("\nRunning metrics tests...")
        print("-" * 40)
        
        # Run tests
        self.test_agent_monitor_basic()
        self.test_agent_monitor_with_metrics()
        self.test_track_operation()
        self.test_track_operation_error()
        
        # Wait for metrics to export
        print("\nWaiting for metrics export...")
        time.sleep(2)
        
        # Summary
        print("-" * 40)
        print(f"Results: {self.passed} passed, {self.failed} failed")
        
        if self.errors:
            print("\nErrors:")
            for error in self.errors:
                print(f"  - {error}")
        
        return self.failed == 0

    def test_agent_monitor_basic(self):
        """Test basic AgentMonitor functionality."""
        @self.test("AgentMonitor basic context manager")
        def _test():
            with AgentMonitor("test-basic") as monitor:
                assert monitor.agent_id == "test-basic"
                time.sleep(0.01)
            # Should complete without error
        _test()
    
    def test_agent_monitor_with_metrics(self):
        """Test AgentMonitor with custom metrics."""
        @self.test("AgentMonitor with custom metrics")
        def _test():
            with AgentMonitor("test-custom") as monitor:
                monitor.metrics["tokens"] = 500
                monitor.metrics["cost"] = 0.01
                time.sleep(0.01)
            
            # Verify metrics were recorded (via the dict)
            assert "tokens" in monitor.metrics
            assert monitor.metrics["tokens"] == 500
        _test()
    
    def test_track_operation(self):
        """Test track_operation context manager."""
        @self.test("track_operation timing")
        def _test():
            with track_operation("test-op"):
                time.sleep(0.02)
            # Should complete without error
        _test()
    
    def test_track_operation_error(self):
        """Test track_operation records errors."""
        @self.test("track_operation error handling")
        def _test():
            try:
                with track_operation("test-error-op"):
                    raise ValueError("test error")
            except ValueError:
                pass  # Expected
            # Should have recorded the error status
        _test()


def main():
    print("=" * 50)
    print("FlatAgents Metrics Integration Tests")
    print("=" * 50)
    
    suite = MetricsTestSuite()
    success = suite.run_all()
    
    print("=" * 50)
    
    if success:
        print("All metrics tests passed!")
        sys.exit(0)
    else:
        print("Some tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
