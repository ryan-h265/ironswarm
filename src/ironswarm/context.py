"""
Rich Context for journey execution.

Provides trace IDs, structured logging, metrics, and resource lifecycle management.
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Callable

import aiohttp

log = logging.getLogger(__name__)


class Context:
    """
    Execution context for journeys with observability and resource management.

    Provides:
    - Unique trace/correlation IDs for distributed tracing
    - Structured logging with context
    - Metrics collection
    - HTTP session management with proper cleanup
    - Lifecycle hooks for resource cleanup
    - Span timing for performance analysis
    """

    def __init__(
        self,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """
        Initialize a new context.

        Args:
            trace_id: Unique trace ID for distributed tracing (auto-generated if None)
            parent_span_id: Parent span ID for nested operations
            metadata: Additional metadata to attach to this context
        """
        # Tracing
        self.trace_id = trace_id or uuid.uuid4().hex
        self.span_id = uuid.uuid4().hex[:16]
        self.parent_span_id = parent_span_id

        # Timing
        self.start_time = time.time()
        self.end_time: float | None = None

        # Metadata
        self.metadata: dict[str, Any] = metadata or {}

        # Resources (for cleanup)
        self._http_session: aiohttp.ClientSession | None = None
        self._cleanup_hooks: list[Callable] = []

        # Metrics
        self.metrics: dict[str, Any] = {}

        # Logging
        self._log_extra = {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
        }

    def get_logger(self, name: str | None = None) -> logging.LoggerAdapter:
        """
        Get a logger with context information automatically included.

        Args:
            name: Logger name (defaults to 'ironswarm.journey')

        Returns:
            LoggerAdapter with trace_id and span_id in all log messages
        """
        logger = logging.getLogger(name or "ironswarm.journey")
        return logging.LoggerAdapter(logger, self._log_extra)

    def log(self, message: str, level: int = logging.INFO, **kwargs):
        """
        Log a message with context information.

        Args:
            message: Message to log
            level: Logging level
            **kwargs: Additional log context
        """
        logger = self.get_logger()
        extra = {**self._log_extra, **kwargs}
        logger.log(level, message, extra=extra)

    def get_http_session(
        self,
        connector: aiohttp.TCPConnector | None = None,
        **session_kwargs
    ) -> aiohttp.ClientSession:
        """
        Get or create an HTTP session for this context.

        The session is automatically cleaned up when the context is closed.

        Args:
            connector: Optional TCP connector (created if not provided)
            **session_kwargs: Additional kwargs for ClientSession

        Returns:
            aiohttp.ClientSession scoped to this context
        """
        if self._http_session is None:
            if connector is None:
                connector = aiohttp.TCPConnector(limit=100)

            # Add tracing
            trace_config = aiohttp.TraceConfig()

            async def on_request_start(session, trace_config_ctx, params):
                trace_config_ctx.start = asyncio.get_event_loop().time()
                self.log(
                    f"HTTP {params.method} {params.url}",
                    level=logging.DEBUG,
                    method=params.method,
                    url=str(params.url),
                )

            async def on_request_end(session, trace_config_ctx, params):
                elapsed = asyncio.get_event_loop().time() - trace_config_ctx.start
                if hasattr(params, "response") and params.response is not None:
                    params.response.elapsed = elapsed  # type: ignore[attr-defined]
                    self.record_metric("http_request_duration_seconds", elapsed)
                    self.log(
                        f"HTTP {params.method} {params.url} -> {params.response.status} ({elapsed:.3f}s)",
                        level=logging.DEBUG,
                        status=params.response.status,
                        duration=elapsed,
                    )

            trace_config.on_request_start.append(on_request_start)
            trace_config.on_request_end.append(on_request_end)

            # Add trace ID to default headers
            headers = session_kwargs.get("headers", {})
            headers["X-Trace-ID"] = self.trace_id
            headers["X-Span-ID"] = self.span_id
            session_kwargs["headers"] = headers

            self._http_session = aiohttp.ClientSession(
                connector=connector,
                trace_configs=[trace_config],
                **session_kwargs
            )

            # Register cleanup hook
            self.add_cleanup_hook(self._cleanup_http_session)

        return self._http_session

    async def _cleanup_http_session(self):
        """Clean up HTTP session if it exists."""
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
            self.log("HTTP session closed", level=logging.DEBUG)

    def record_metric(self, name: str, value: Any, labels: dict[str, str] | None = None):
        """
        Record a metric value.

        Args:
            name: Metric name
            value: Metric value
            labels: Optional labels/tags for the metric
        """
        if name not in self.metrics:
            self.metrics[name] = []

        metric_entry = {
            "value": value,
            "timestamp": time.time(),
            "labels": labels or {},
        }
        self.metrics[name].append(metric_entry)

    def add_cleanup_hook(self, hook: Callable):
        """
        Add a cleanup hook to be called when context is closed.

        Args:
            hook: Async or sync callable to run on cleanup
        """
        self._cleanup_hooks.append(hook)

    async def close(self):
        """
        Close the context and clean up all resources.

        Runs all registered cleanup hooks in reverse order.
        """
        self.end_time = time.time()

        # Run cleanup hooks in reverse order (LIFO)
        for hook in reversed(self._cleanup_hooks):
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
            except Exception as e:
                log.error(f"Error in cleanup hook: {e}", exc_info=True)

        self._cleanup_hooks.clear()

    def elapsed(self) -> float:
        """Get elapsed time for this context in seconds."""
        end = self.end_time or time.time()
        return end - self.start_time

    def create_child_context(self, **kwargs) -> "Context":
        """
        Create a child context for nested operations.

        Args:
            **kwargs: Additional arguments for child context

        Returns:
            New Context with this context as parent
        """
        return Context(
            trace_id=self.trace_id,
            parent_span_id=self.span_id,
            metadata=kwargs.pop("metadata", {**self.metadata}),
            **kwargs
        )

    async def __aenter__(self):
        """Support async context manager protocol."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Support async context manager protocol with cleanup."""
        await self.close()
        return False

    def __repr__(self):
        return (
            f"Context(trace_id={self.trace_id[:8]}..., "
            f"span_id={self.span_id}, elapsed={self.elapsed():.3f}s)"
        )
