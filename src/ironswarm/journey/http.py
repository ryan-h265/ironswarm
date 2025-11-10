"""
HTTP journey utilities using rich Context for observability.

Provides decorators for HTTP-based journeys with automatic:
- HTTP session management with connection pooling
- Distributed tracing headers
- Request/response logging
- Metrics collection
"""

import functools

import aiohttp


def http_session(
        pool_size: int = 100,
        auth: aiohttp.BasicAuth | None = None,
        headers: dict[str, str] | None = None
    ):
    """
    Decorator that provides an HTTP session to journey functions via Context.

    Uses Context.get_http_session() which provides:
    - Automatic connection pooling
    - Distributed tracing headers (X-Trace-ID, X-Span-ID)
    - Request timing and logging
    - Proper cleanup on context close

    Args:
        pool_size: Max number of concurrent connections (default: 100)
        auth: Optional basic authentication
        headers: Optional default headers (merged with trace headers)

    Example:
        @http_session()
        async def my_journey(context):
            async with context.session.get("https://api.example.com") as resp:
                data = await resp.json()
                # resp.elapsed contains request duration
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(context, *args, **kwargs):
            # Build session kwargs
            connector = aiohttp.TCPConnector(limit=pool_size)
            session_kwargs = {"connector": connector}

            if auth:
                session_kwargs["auth"] = auth

            # Merge headers with context's trace headers
            if headers:
                session_kwargs["headers"] = headers

            # Get HTTP session from context (creates if needed, adds trace headers)
            context.session = context.get_http_session(**session_kwargs)

            return await func(context, *args, **kwargs)
        return wrapper
    return decorator

