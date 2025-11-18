"""
Metrics package providing local aggregation primitives for journeys.

Currently exposes a single collector instance that can be reused across the
process. The collector keeps Prometheus-compatible counter and histogram
structures so future exporters can reuse the same data without refactors.
"""

from .collector import (
    DEFAULT_LATENCY_BUCKETS,
    CounterMetric,
    HistogramMetric,
    MetricCollector,
    collector,
    get_collector,
)
from .graphs import generate_graphs
from .report import format_report, summarize_snapshot
from . import aggregator

# Note: aggregator is available as a submodule but not imported here
# to avoid circular imports. Use: from ironswarm.metrics import aggregator

__all__ = [
    "CounterMetric",
    "HistogramMetric",
    "MetricCollector",
    "DEFAULT_LATENCY_BUCKETS",
    "format_report",
    "summarize_snapshot",
    "generate_graphs",
    "collector",
    "get_collector",
    "aggregator",
]
