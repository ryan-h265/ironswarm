"""
Journey logging utilities using rich Context for observability.

Provides decorators for journey-specific logging with automatic:
- Trace ID correlation
- Structured logging format
- Journey-specific log context
"""

import functools
import logging


def log_output(func):
    """
    Decorator that enhances context.log() for journey execution.

    The Context already provides structured logging via context.log().
    This decorator ensures the journey name is included in log context.

    Example:
        @log_output
        async def my_journey(context):
            context.log("Processing request", status=200, duration=0.5)
            # Logs include: trace_id, span_id, journey_name, status, duration
    """
    @functools.wraps(func)
    async def wrapper(context, *args, **kwargs):
        # Add journey name to context metadata
        context.metadata["journey_name"] = func.__name__

        # Create convenience method that includes journey context
        original_log = context.log

        def enhanced_log(message: str, level: int = logging.INFO, **kwargs):
            # Add journey name to all log calls
            kwargs["journey"] = func.__name__
            return original_log(message, level=level, **kwargs)

        # Override context.log with enhanced version
        context.log = enhanced_log

        return await func(context, *args, **kwargs)

    return wrapper

