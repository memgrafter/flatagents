# Integration Tests

This directory contains integration tests that require external dependencies or isolated environments.

## Running All Tests

```bash
./run.sh
```

## Test Suites

### metrics/
Tests OpenTelemetry metrics integration with console exporter.

```bash
cd metrics && ./run.sh
```

## Adding New Tests

1. Create a new directory: `tests/integration/<test-name>/`
2. Add a `run.sh` script that:
   - Sets up any required environment
   - Returns 0 on success, non-zero on failure
3. The main `run.sh` will auto-discover and run it
