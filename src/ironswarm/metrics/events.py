from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

from ironswarm.metrics.collector import collector


def _scenario_labels(context) -> dict[str, str]:
    metadata = getattr(context, "metadata", {}) or {}
    scenario = str(metadata.get("scenario", "unknown"))
    journey = str(
        metadata.get("journey_name")
        or metadata.get("journey_spec")
        or metadata.get("journey", "unknown")
    )
    labels: dict[str, str] = {
        "scenario": scenario,
        "journey": journey,
    }
    node_id = metadata.get("node") or metadata.get("node_id")
    if node_id:
        labels["node"] = str(node_id)
    return labels


def _http_labels(context, method: str, url: Any, status: int | str) -> dict[str, str]:
    labels = _scenario_labels(context)
    labels["method"] = method.upper()
    labels["status"] = str(status)

    host = None
    path = None
    if hasattr(url, "host"):
        host = getattr(url, "host", None)
        path = getattr(url, "path", None)
    else:
        parsed = urlparse(str(url))
        host = parsed.netloc
        path = parsed.path

    if host:
        labels["host"] = host
    if path:
        labels["path"] = path or "/"

    return labels


def record_http_request(
    context,
    method: str,
    url: Any,
    status: int,
    duration: float,
    timestamp: float | None = None,
) -> None:
    if timestamp is None:
        timestamp = time.time()
    metric = collector
    labels = _http_labels(context, method, url, status)
    metric.inc("ironswarm_http_requests_total", labels=labels)
    if int(status) >= 400:
        metric.inc("ironswarm_http_errors_total", labels=labels)
    metric.observe("ironswarm_http_request_duration_seconds", duration, labels=labels)
    metric.record_event(
        "http_request",
        {
            "timestamp": timestamp,
            "duration": duration,
            "labels": labels,
        },
    )


def record_journey_success(context, duration: float) -> None:
    labels = _scenario_labels(context)
    collector.inc("ironswarm_journey_executions_total", labels=labels)
    collector.observe("ironswarm_journey_duration_seconds", duration, labels=labels)


def record_journey_failure(context, duration: float, error: BaseException | None = None) -> None:
    error_type = error.__class__.__name__ if error else "UnknownError"
    base_labels = _scenario_labels(context)
    collector.inc("ironswarm_journey_executions_total", labels=base_labels)
    collector.inc(
        "ironswarm_journey_failures_total",
        labels={**base_labels, "error": error_type},
    )
    if duration >= 0:
        collector.observe("ironswarm_journey_duration_seconds", duration, labels=base_labels)
