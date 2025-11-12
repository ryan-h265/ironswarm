import asyncio
import logging
import time
from unittest.mock import AsyncMock

import aiohttp
import pytest

from ironswarm.context import Context

# ============================================================================
# Initialization Tests
# ============================================================================


def test_context_initialization_with_defaults():
    """Test context initializes with auto-generated IDs."""
    ctx = Context()

    assert ctx.trace_id is not None
    assert len(ctx.trace_id) == 32  # UUID hex format
    assert ctx.span_id is not None
    assert len(ctx.span_id) == 16
    assert ctx.parent_span_id is None
    assert ctx.metadata == {}
    assert ctx.metrics == {}
    assert ctx._http_session is None
    assert ctx._cleanup_hooks == []
    assert ctx.start_time > 0
    assert ctx.end_time is None


def test_context_initialization_with_custom_trace_id():
    """Test context accepts custom trace ID."""
    custom_trace_id = "custom-trace-123"
    ctx = Context(trace_id=custom_trace_id)

    assert ctx.trace_id == custom_trace_id
    assert ctx.span_id is not None
    assert ctx.parent_span_id is None


def test_context_initialization_with_parent_span():
    """Test context accepts parent span ID."""
    parent_span = "parent-span-456"
    ctx = Context(parent_span_id=parent_span)

    assert ctx.parent_span_id == parent_span
    assert ctx.span_id != parent_span  # Should have its own span ID


def test_context_initialization_with_metadata():
    """Test context accepts custom metadata."""
    metadata = {"user_id": "123", "request_type": "load_test"}
    ctx = Context(metadata=metadata)

    assert ctx.metadata == metadata
    # Context stores the same reference (not a copy)
    assert ctx.metadata is metadata


def test_context_repr():
    """Test context string representation."""
    ctx = Context(trace_id="abcdef123456")

    repr_str = repr(ctx)
    assert "trace_id=abcdef12" in repr_str  # First 8 chars
    assert f"span_id={ctx.span_id}" in repr_str
    assert "elapsed=" in repr_str


# ============================================================================
# Logging Tests
# ============================================================================


def test_get_logger_returns_adapter_with_context():
    """Test get_logger returns LoggerAdapter with trace context."""
    ctx = Context(trace_id="trace123")
    logger = ctx.get_logger()

    assert isinstance(logger, logging.LoggerAdapter)
    assert logger.extra["trace_id"] == "trace123"
    assert logger.extra["span_id"] == ctx.span_id


def test_get_logger_with_custom_name():
    """Test get_logger accepts custom logger name."""
    ctx = Context()
    logger = ctx.get_logger("custom.logger")

    assert logger.logger.name == "custom.logger"


def test_log_method_includes_context(caplog):
    """Test log method includes trace context in log records."""
    ctx = Context(trace_id="log-trace-123")

    with caplog.at_level(logging.INFO):
        ctx.log("Test message", level=logging.INFO)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert "Test message" in record.message
    # Note: extra fields are in the record but not automatically in message
    assert hasattr(record, "trace_id") and record.trace_id == "log-trace-123"


def test_log_method_with_additional_kwargs():
    """Test log method accepts additional context kwargs."""
    ctx = Context()

    # The log method should accept additional kwargs and pass them to the logger
    # We verify this by ensuring the call doesn't raise an exception
    ctx.log("Request processed", level=logging.DEBUG, user_id="456", status="success")

    # The kwargs are merged into the extra dict that's passed to the logger
    # This is correct behavior - the method signature accepts them


# ============================================================================
# HTTP Session Management Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_http_session_creates_session():
    """Test get_http_session creates a new session on first call."""
    ctx = Context()

    session = ctx.get_http_session()

    assert isinstance(session, aiohttp.ClientSession)
    assert session is ctx._http_session
    assert not session.closed

    await ctx.close()


@pytest.mark.asyncio
async def test_get_http_session_returns_same_instance():
    """Test subsequent get_http_session calls return the same session."""
    ctx = Context()

    session1 = ctx.get_http_session()
    session2 = ctx.get_http_session()

    assert session1 is session2

    await ctx.close()


@pytest.mark.asyncio
async def test_http_session_includes_trace_headers():
    """Test HTTP session includes trace ID headers."""
    ctx = Context(trace_id="header-trace-789")

    session = ctx.get_http_session()

    assert "X-Trace-ID" in session.headers
    assert session.headers["X-Trace-ID"] == "header-trace-789"
    assert "X-Span-ID" in session.headers
    assert session.headers["X-Span-ID"] == ctx.span_id

    await ctx.close()


@pytest.mark.asyncio
async def test_http_session_accepts_custom_connector():
    """Test get_http_session accepts custom connector."""
    ctx = Context()
    custom_connector = aiohttp.TCPConnector(limit=50)

    session = ctx.get_http_session(connector=custom_connector)

    assert session.connector is custom_connector

    await ctx.close()


@pytest.mark.asyncio
async def test_http_session_accepts_additional_kwargs():
    """Test get_http_session accepts additional session kwargs."""
    ctx = Context()
    custom_headers = {"Authorization": "Bearer token"}

    session = ctx.get_http_session(headers=custom_headers)

    # Should have both custom and trace headers
    assert "Authorization" in session.headers
    assert "X-Trace-ID" in session.headers

    await ctx.close()


@pytest.mark.asyncio
async def test_http_session_cleanup_hook_registered():
    """Test HTTP session creation registers cleanup hook."""
    ctx = Context()

    assert len(ctx._cleanup_hooks) == 0

    ctx.get_http_session()

    assert len(ctx._cleanup_hooks) == 1

    await ctx.close()


@pytest.mark.asyncio
async def test_http_session_closed_on_context_close():
    """Test HTTP session is closed when context closes."""
    ctx = Context()
    session = ctx.get_http_session()

    assert not session.closed

    await ctx.close()

    assert session.closed


@pytest.mark.asyncio
async def test_cleanup_http_session_idempotent():
    """Test HTTP session cleanup can be called multiple times safely."""
    ctx = Context()
    session = ctx.get_http_session()

    # Close once
    await ctx._cleanup_http_session()
    assert session.closed

    # Close again should not raise
    await ctx._cleanup_http_session()
    assert session.closed


# ============================================================================
# Metrics Tests
# ============================================================================


def test_record_metric_stores_value():
    """Test record_metric stores metric values."""
    ctx = Context()

    ctx.record_metric("requests_total", 1)

    assert "requests_total" in ctx.metrics
    assert len(ctx.metrics["requests_total"]) == 1
    assert ctx.metrics["requests_total"][0]["value"] == 1


def test_record_metric_stores_multiple_values():
    """Test record_metric can store multiple values for same metric."""
    ctx = Context()

    ctx.record_metric("response_time", 0.123)
    ctx.record_metric("response_time", 0.456)
    ctx.record_metric("response_time", 0.789)

    assert len(ctx.metrics["response_time"]) == 3
    assert ctx.metrics["response_time"][0]["value"] == 0.123
    assert ctx.metrics["response_time"][1]["value"] == 0.456
    assert ctx.metrics["response_time"][2]["value"] == 0.789


def test_record_metric_includes_timestamp():
    """Test record_metric includes timestamp for each entry."""
    ctx = Context()
    before = time.time()

    ctx.record_metric("test_metric", 42)

    after = time.time()
    timestamp = ctx.metrics["test_metric"][0]["timestamp"]
    assert before <= timestamp <= after


def test_record_metric_with_labels():
    """Test record_metric stores labels."""
    ctx = Context()
    labels = {"method": "GET", "status": "200"}

    ctx.record_metric("http_requests", 1, labels=labels)

    metric = ctx.metrics["http_requests"][0]
    assert metric["labels"] == labels


def test_record_metric_without_labels():
    """Test record_metric works without labels."""
    ctx = Context()

    ctx.record_metric("simple_counter", 5)

    metric = ctx.metrics["simple_counter"][0]
    assert metric["labels"] == {}


# ============================================================================
# Cleanup Hook Tests
# ============================================================================


@pytest.mark.asyncio
async def test_add_cleanup_hook_registers_hook():
    """Test add_cleanup_hook registers a cleanup function."""
    ctx = Context()
    hook = AsyncMock()

    ctx.add_cleanup_hook(hook)

    assert hook in ctx._cleanup_hooks


@pytest.mark.asyncio
async def test_cleanup_hooks_run_on_close():
    """Test cleanup hooks are executed when context closes."""
    ctx = Context()
    hook1 = AsyncMock()
    hook2 = AsyncMock()

    ctx.add_cleanup_hook(hook1)
    ctx.add_cleanup_hook(hook2)

    await ctx.close()

    hook1.assert_called_once()
    hook2.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_hooks_run_in_reverse_order():
    """Test cleanup hooks run in LIFO order."""
    ctx = Context()
    call_order = []

    async def hook1():
        call_order.append(1)

    async def hook2():
        call_order.append(2)

    async def hook3():
        call_order.append(3)

    ctx.add_cleanup_hook(hook1)
    ctx.add_cleanup_hook(hook2)
    ctx.add_cleanup_hook(hook3)

    await ctx.close()

    # Should run in reverse order: 3, 2, 1
    assert call_order == [3, 2, 1]


@pytest.mark.asyncio
async def test_cleanup_hooks_support_sync_functions():
    """Test cleanup hooks work with synchronous functions."""
    ctx = Context()
    sync_called = False

    def sync_hook():
        nonlocal sync_called
        sync_called = True

    ctx.add_cleanup_hook(sync_hook)
    await ctx.close()

    assert sync_called is True


@pytest.mark.asyncio
async def test_cleanup_hooks_support_async_functions():
    """Test cleanup hooks work with async functions."""
    ctx = Context()
    async_called = False

    async def async_hook():
        nonlocal async_called
        async_called = True
        await asyncio.sleep(0)  # Ensure it's truly async

    ctx.add_cleanup_hook(async_hook)
    await ctx.close()

    assert async_called is True


@pytest.mark.asyncio
async def test_cleanup_hooks_errors_dont_stop_other_hooks(caplog):
    """Test errors in cleanup hooks don't prevent other hooks from running."""
    ctx = Context()
    hook1_called = False
    hook3_called = False

    async def hook1():
        nonlocal hook1_called
        hook1_called = True

    async def hook2_fails():
        raise ValueError("Hook failed!")

    async def hook3():
        nonlocal hook3_called
        hook3_called = True

    ctx.add_cleanup_hook(hook1)
    ctx.add_cleanup_hook(hook2_fails)
    ctx.add_cleanup_hook(hook3)

    with caplog.at_level(logging.ERROR):
        await ctx.close()

    # All hooks should have been attempted
    assert hook1_called is True
    assert hook3_called is True
    # Error should be logged
    assert any("Error in cleanup hook" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_cleanup_hooks_cleared_after_close():
    """Test cleanup hooks are cleared after context closes."""
    ctx = Context()
    hook = AsyncMock()

    ctx.add_cleanup_hook(hook)
    assert len(ctx._cleanup_hooks) == 1

    await ctx.close()

    assert len(ctx._cleanup_hooks) == 0


# ============================================================================
# Lifecycle Tests
# ============================================================================


def test_elapsed_before_close():
    """Test elapsed() calculates time before close."""
    ctx = Context()
    time.sleep(0.01)  # Small delay

    elapsed = ctx.elapsed()

    assert elapsed >= 0.01
    assert ctx.end_time is None  # Not closed yet


def test_elapsed_after_close():
    """Test elapsed() uses end_time after close."""

    async def test():
        ctx = Context()
        time.sleep(0.01)
        await ctx.close()

        assert ctx.end_time is not None
        elapsed = ctx.elapsed()
        # Should use end_time, not current time
        assert elapsed == ctx.end_time - ctx.start_time

    asyncio.run(test())


def test_close_sets_end_time():
    """Test close() sets end_time."""

    async def test():
        ctx = Context()
        assert ctx.end_time is None

        await ctx.close()

        assert ctx.end_time is not None
        assert ctx.end_time >= ctx.start_time

    asyncio.run(test())


# ============================================================================
# Child Context Tests
# ============================================================================


def test_create_child_context_preserves_trace_id():
    """Test child context inherits trace ID from parent."""
    parent = Context(trace_id="parent-trace-123")
    child = parent.create_child_context()

    assert child.trace_id == "parent-trace-123"
    assert child.span_id != parent.span_id  # Different span
    assert child.parent_span_id == parent.span_id


def test_create_child_context_inherits_metadata():
    """Test child context inherits parent metadata."""
    parent = Context(metadata={"user_id": "123", "session": "abc"})
    child = parent.create_child_context()

    assert child.metadata == parent.metadata
    # Should be a copy, not the same reference
    assert child.metadata is not parent.metadata


def test_create_child_context_with_custom_metadata():
    """Test child context can override metadata."""
    parent = Context(metadata={"user_id": "123"})
    custom_metadata = {"request_id": "456"}
    child = parent.create_child_context(metadata=custom_metadata)

    assert child.metadata == custom_metadata
    assert child.metadata != parent.metadata


def test_child_context_independent_metrics():
    """Test child context has independent metrics."""
    parent = Context()
    parent.record_metric("parent_metric", 1)

    child = parent.create_child_context()
    child.record_metric("child_metric", 2)

    assert "parent_metric" in parent.metrics
    assert "parent_metric" not in child.metrics
    assert "child_metric" in child.metrics
    assert "child_metric" not in parent.metrics


@pytest.mark.asyncio
async def test_child_context_independent_cleanup():
    """Test child and parent contexts have independent cleanup."""
    parent = Context()
    parent_hook = AsyncMock()
    parent.add_cleanup_hook(parent_hook)

    child = parent.create_child_context()
    child_hook = AsyncMock()
    child.add_cleanup_hook(child_hook)

    await child.close()
    child_hook.assert_called_once()
    parent_hook.assert_not_called()

    await parent.close()
    parent_hook.assert_called_once()


# ============================================================================
# Async Context Manager Tests
# ============================================================================


@pytest.mark.asyncio
async def test_context_manager_returns_self():
    """Test context manager __aenter__ returns self."""
    ctx = Context()

    async with ctx as cm:
        assert cm is ctx


@pytest.mark.asyncio
async def test_context_manager_calls_close_on_exit():
    """Test context manager calls close() on exit."""
    ctx = Context()
    hook = AsyncMock()
    ctx.add_cleanup_hook(hook)

    async with ctx:
        hook.assert_not_called()

    hook.assert_called_once()


@pytest.mark.asyncio
async def test_context_manager_closes_on_exception():
    """Test context manager closes even when exception occurs."""
    ctx = Context()
    hook = AsyncMock()
    ctx.add_cleanup_hook(hook)

    with pytest.raises(ValueError):
        async with ctx:
            raise ValueError("Test exception")

    # Should still have called cleanup
    hook.assert_called_once()


@pytest.mark.asyncio
async def test_context_manager_sets_end_time():
    """Test context manager sets end_time on exit."""
    ctx = Context()

    async with ctx:
        assert ctx.end_time is None

    assert ctx.end_time is not None


@pytest.mark.asyncio
async def test_context_manager_closes_http_session():
    """Test context manager closes HTTP session on exit."""
    async with Context() as ctx:
        session = ctx.get_http_session()
        assert not session.closed

    assert session.closed


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_full_lifecycle_with_http_and_metrics():
    """Test complete context lifecycle with HTTP session and metrics."""
    async with Context(trace_id="integration-test") as ctx:
        # Create HTTP session
        session = ctx.get_http_session()
        assert not session.closed

        # Record some metrics
        ctx.record_metric("test_metric", 123)
        ctx.record_metric("test_metric", 456)

        # Add custom cleanup hook
        cleanup_called = False

        async def custom_cleanup():
            nonlocal cleanup_called
            cleanup_called = True

        ctx.add_cleanup_hook(custom_cleanup)

        # Create child context
        child = ctx.create_child_context()
        assert child.trace_id == "integration-test"
        assert child.parent_span_id == ctx.span_id

    # After exit, everything should be cleaned up
    assert session.closed
    assert cleanup_called is True
    assert len(ctx.metrics["test_metric"]) == 2
    assert ctx.end_time is not None
