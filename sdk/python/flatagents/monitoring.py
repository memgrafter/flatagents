"""
Monitoring and observability utilities for FlatAgents.

Provides standardized logging configuration and OpenTelemetry-based metrics.
"""

import logging
import os
import sys
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Logging Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Global logger registry
_loggers: Dict[str, logging.Logger] = {}
_logging_configured = False


def setup_logging(
    level: Optional[str] = None,
    format: Optional[str] = None,
    force: bool = False
) -> None:
    """
    Configure SDK-wide logging with sensible defaults.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               Defaults to FLATAGENTS_LOG_LEVEL env var or INFO.
        format: Log format style. Options:
                - 'standard': Human-readable with timestamps
                - 'json': Structured JSON logging
                - 'simple': Just level and message
                - Custom format string
                Defaults to FLATAGENTS_LOG_FORMAT env var or 'standard'.
        force: If True, reconfigure even if already configured.
    
    Example:
        >>> from flatagents import setup_logging
        >>> setup_logging(level='DEBUG')
        >>> # Or via environment:
        >>> # export FLATAGENTS_LOG_LEVEL=DEBUG
        >>> # export FLATAGENTS_LOG_FORMAT=json
    """
    global _logging_configured
    
    if _logging_configured and not force:
        return
    
    # Determine log level
    if level is None:
        level = os.getenv('FLATAGENTS_LOG_LEVEL', 'INFO').upper()
    
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Determine format
    if format is None:
        format = os.getenv('FLATAGENTS_LOG_FORMAT', 'standard')
    
    if format == 'json':
        # Structured JSON logging - note: message content should be escaped by caller for true JSON safety
        log_format = '{"time":"%(asctime)s","name":"%(name)s","level":"%(levelname)s","message":%(message)s}'
    elif format == 'simple':
        log_format = '%(levelname)s - %(message)s'
    elif format == 'standard':
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    else:
        # Custom format string
        log_format = format
    
    # Configure root logger for the SDK
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt='%Y-%m-%d %H:%M:%S',
        stream=sys.stdout,
        force=force
    )
    
    _logging_configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a properly configured logger for a module.
    
    Args:
        name: Logger name (typically __name__ from the calling module)
    
    Returns:
        Configured logger instance
    
    Example:
        >>> from flatagents import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Agent started")
    """
    if name not in _loggers:
        # Ensure logging is configured
        if not _logging_configured:
            setup_logging()
        
        logger = logging.getLogger(name)
        _loggers[name] = logger
    
    return _loggers[name]


# ─────────────────────────────────────────────────────────────────────────────
# Metrics with OpenTelemetry
# ─────────────────────────────────────────────────────────────────────────────

# Lazy imports for OpenTelemetry (optional dependency)
_otel_available = False
_meter = None
_metrics_enabled = False
_cached_histograms: Dict[str, Any] = {}  # Cache for histogram instruments

try:
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    _otel_available = True
except ImportError:
    _otel_available = False


def _init_metrics() -> None:
    """Initialize OpenTelemetry metrics if enabled and available."""
    global _meter, _metrics_enabled
    
    # Check if metrics should be enabled
    enabled = os.getenv('FLATAGENTS_METRICS_ENABLED', 'false').lower() in ('true', '1', 'yes')
    
    if not enabled:
        _metrics_enabled = False
        return
    
    if not _otel_available:
        logger = get_logger(__name__)
        logger.warning(
            "Metrics enabled but OpenTelemetry not available. "
            "Install with: pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp"
        )
        _metrics_enabled = False
        return
    
    try:
        # Get service name from environment or use default
        service_name = os.getenv('OTEL_SERVICE_NAME', 'flatagents')
        
        # Create resource with service name
        resource = Resource(attributes={
            SERVICE_NAME: service_name
        })
        
        # Check which exporter to use
        exporter_type = os.getenv('OTEL_METRICS_EXPORTER', 'otlp').lower()
        
        if exporter_type == 'console':
            # Use console exporter for testing/debugging
            try:
                from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
                exporter = ConsoleMetricExporter()
            except ImportError:
                logger = get_logger(__name__)
                logger.warning("Console exporter not available, falling back to OTLP")
                exporter = OTLPMetricExporter(
                    endpoint=os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT'),
                )
        else:
            # Configure OTLP exporter (supports Datadog, Honeycomb, etc.)
            exporter = OTLPMetricExporter(
                endpoint=os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT'),
                # Headers can be set via OTEL_EXPORTER_OTLP_HEADERS env var
            )
        
        # Create meter provider with periodic export
        reader = PeriodicExportingMetricReader(
            exporter=exporter,
            export_interval_millis=int(os.getenv('OTEL_METRIC_EXPORT_INTERVAL', '5000' if exporter_type == 'console' else '60000'))
        )
        
        provider = MeterProvider(
            resource=resource,
            metric_readers=[reader]
        )
        
        metrics.set_meter_provider(provider)
        _meter = metrics.get_meter(__name__)
        _metrics_enabled = True
        
        logger = get_logger(__name__)
        logger.info(f"OpenTelemetry metrics enabled for service: {service_name}")
        
    except Exception as e:
        logger = get_logger(__name__)
        logger.warning(f"Failed to initialize OpenTelemetry metrics: {e}")
        _metrics_enabled = False


def get_meter():
    """
    Get the OpenTelemetry meter for creating custom metrics.
    
    Returns:
        OpenTelemetry Meter instance or None if metrics disabled
    
    Example:
        >>> from flatagents import get_meter
        >>> meter = get_meter()
        >>> if meter:
        ...     counter = meter.create_counter("my_custom_metric")
        ...     counter.add(1, {"attribute": "value"})
    """
    global _meter
    
    if _meter is None and not _metrics_enabled:
        _init_metrics()
    
    return _meter


class AgentMonitor:
    """
    Context manager for tracking agent execution metrics.
    
    Automatically tracks:
    - Execution duration
    - Success/failure status
    - Custom metrics via the metrics dict
    
    Example:
        >>> from flatagents import AgentMonitor
        >>> with AgentMonitor("my-agent") as monitor:
        ...     # Do agent work
        ...     monitor.metrics["tokens"] = 1500
        ...     monitor.metrics["cost"] = 0.03
        >>> # Metrics automatically emitted on exit
    """
    
    def __init__(self, agent_id: str, extra_attributes: Optional[Dict[str, Any]] = None):
        """
        Initialize the monitor.
        
        Args:
            agent_id: Identifier for this agent/operation
            extra_attributes: Additional attributes to attach to all metrics
        """
        self.agent_id = agent_id
        self.start_time = None
        self.metrics: Dict[str, Any] = {}
        self.extra_attributes = extra_attributes or {}
        self.logger = get_logger(f"flatagents.monitor.{agent_id}")
        
        # Get or create metric instruments
        self._meter = get_meter()
        if self._meter:
            self._duration_histogram = self._meter.create_histogram(
                "flatagents.agent.duration",
                unit="ms",
                description="Agent execution duration"
            )
            self._token_counter = self._meter.create_counter(
                "flatagents.agent.tokens",
                description="Tokens used by agent"
            )
            self._cost_counter = self._meter.create_counter(
                "flatagents.agent.cost",
                description="Estimated cost of agent execution"
            )
            self._status_counter = self._meter.create_counter(
                "flatagents.agent.executions",
                description="Agent execution count by status"
            )
    
    def __enter__(self):
        """Start monitoring."""
        self.start_time = time.time()
        self.logger.debug(f"Agent {self.agent_id} started")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop monitoring and emit metrics."""
        duration_ms = (time.time() - self.start_time) * 1000
        status = "success" if exc_type is None else "error"
        
        # Build attributes
        attributes = {
            "agent_id": self.agent_id,
            "status": status,
            **self.extra_attributes
        }
        
        if exc_type is not None:
            attributes["error_type"] = exc_type.__name__
        
        # Log completion
        self.logger.info(
            f"Agent {self.agent_id} completed in {duration_ms:.2f}ms - {status}"
        )
        
        # Emit metrics if enabled
        if self._meter:
            self._duration_histogram.record(duration_ms, attributes)
            self._status_counter.add(1, attributes)
            
            if "tokens" in self.metrics:
                self._token_counter.add(self.metrics["tokens"], attributes)
            
            if "cost" in self.metrics:
                self._cost_counter.add(self.metrics["cost"], attributes)
        
        # Don't suppress exceptions
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Convenience context manager for temporary metrics
# ─────────────────────────────────────────────────────────────────────────────

@contextmanager
def track_operation(operation_name: str, **attributes):
    """
    Track duration of an operation.
    
    Args:
        operation_name: Name of the operation
        **attributes: Additional attributes to attach
    
    Example:
        >>> from flatagents.monitoring import track_operation
        >>> with track_operation("llm_call", model="gpt-4"):
        ...     response = await llm.call(messages)
    """
    meter = get_meter()
    start_time = time.time()
    
    try:
        yield
        status = "success"
    except Exception as e:
        status = "error"
        attributes["error_type"] = type(e).__name__
        raise
    finally:
        duration_ms = (time.time() - start_time) * 1000
        
        if meter:
            # Cache histogram to avoid recreating on each call
            cache_key = f"flatagents.{operation_name}.duration"
            if cache_key not in _cached_histograms:
                _cached_histograms[cache_key] = meter.create_histogram(
                    cache_key,
                    unit="ms",
                    description=f"Duration of {operation_name}"
                )
            _cached_histograms[cache_key].record(duration_ms, {**attributes, "status": status})


__all__ = [
    "setup_logging",
    "get_logger",
    "get_meter",
    "AgentMonitor",
    "track_operation",
]
