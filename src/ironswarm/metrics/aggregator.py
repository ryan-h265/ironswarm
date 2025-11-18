"""Helpers for aggregating distributed metrics snapshots."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from time import time
from typing import Any, Iterable, Mapping, Sequence

from ironswarm.metrics_snapshot import MetricsSnapshot

LabelsType = Mapping[str, str] | None
_LabelKey = tuple[tuple[str, str], ...]


def _normalize_labels(labels: LabelsType) -> _LabelKey:
    if not labels:
        return tuple()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


@dataclass
class _CounterAccumulator:
    description: str = ""
    samples: dict[_LabelKey, float] = field(default_factory=dict)
    labels: dict[_LabelKey, dict[str, str]] = field(default_factory=dict)


@dataclass
class _HistogramSampleAccumulator:
    counts: list[float]
    labels: dict[str, str]
    sum: float = 0.0
    count: float = 0.0


@dataclass
class _HistogramAccumulator:
    description: str = ""
    buckets: tuple[float, ...] = field(default_factory=tuple)
    samples: dict[_LabelKey, _HistogramSampleAccumulator] = field(default_factory=dict)


def aggregate_snapshots(snapshots: Iterable[MetricsSnapshot]) -> dict[str, Any]:
    """Public helper retained for backwards compatibility."""
    return _aggregate_snapshots(list(snapshots))


def get_cluster_snapshot(snapshots: Iterable[MetricsSnapshot]) -> dict[str, Any]:
    """Aggregate metrics from all snapshots into a single view."""
    return aggregate_snapshots(snapshots)


def query_time_window(
    snapshots: Iterable[MetricsSnapshot],
    *,
    start_timestamp: int | None = None,
    end_timestamp: int | None = None,
) -> dict:
    """Aggregate metrics within the requested time window."""
    filtered: list[MetricsSnapshot] = []
    for snapshot in snapshots:
        if start_timestamp is not None and snapshot.timestamp < start_timestamp:
            continue
        if end_timestamp is not None and snapshot.timestamp > end_timestamp:
            continue
        filtered.append(snapshot)
    return _aggregate_snapshots(filtered)


def get_per_node_snapshots(snapshots: Iterable[MetricsSnapshot]) -> list[dict]:
    """Return the most recent snapshot for each node."""
    latest: dict[str, MetricsSnapshot] = {}
    for snapshot in snapshots:
        current = latest.get(snapshot.node_identity)
        if current is None or snapshot.timestamp > current.timestamp:
            latest[snapshot.node_identity] = snapshot

    per_node: list[dict] = []
    for node_identity in sorted(latest.keys()):
        snapshot = latest[node_identity]
        data = snapshot.snapshot_data or {}
        per_node.append(
            {
                "node_identity": node_identity,
                "timestamp": snapshot.timestamp,
                "counters": data.get("counters", {}),
                "histograms": data.get("histograms", {}),
                "events": data.get("events", {}),
            }
        )
    return per_node


def get_time_series(
    snapshots: Iterable[MetricsSnapshot],
    metric_name: str,
    metric_type: str = "counter",
) -> list[dict[str, Any]]:
    """Return a time series for a specific metric across nodes."""
    series: list[dict[str, Any]] = []
    for snapshot in sorted(snapshots, key=lambda s: s.timestamp):
        data = snapshot.snapshot_data or {}
        if metric_type == "counter":
            metric = data.get("counters", {}).get(metric_name)
            if metric:
                series.append(
                    {
                        "timestamp": snapshot.timestamp,
                        "node_identity": snapshot.node_identity,
                        "samples": metric.get("samples", []),
                    }
                )
        elif metric_type == "histogram":
            metric = data.get("histograms", {}).get(metric_name)
            if metric:
                series.append(
                    {
                        "timestamp": snapshot.timestamp,
                        "node_identity": snapshot.node_identity,
                        "samples": metric.get("samples", []),
                    }
                )
        elif metric_type == "event":
            events = data.get("events", {}).get(metric_name, [])
            if events:
                series.append(
                    {
                        "timestamp": snapshot.timestamp,
                        "node_identity": snapshot.node_identity,
                        "events": events,
                    }
                )
    return series


def _aggregate_snapshots(snapshots: Sequence[MetricsSnapshot]) -> dict:
    counters: dict[str, _CounterAccumulator] = {}
    histograms: dict[str, _HistogramAccumulator] = {}
    events: defaultdict[str, list] = defaultdict(list)
    node_ids: set[str] = set()
    latest_timestamp = 0

    for snapshot in snapshots:
        node_ids.add(snapshot.node_identity)
        latest_timestamp = max(latest_timestamp, snapshot.timestamp)
        data = snapshot.snapshot_data or {}
        _merge_counters(counters, data.get("counters", {}))
        _merge_histograms(histograms, data.get("histograms", {}))
        _merge_events(events, data.get("events", {}))

    aggregated = {
        "timestamp": latest_timestamp or int(time()),
        "node_count": len(node_ids),
        "counters": _finalize_counters(counters),
        "histograms": _finalize_histograms(histograms),
        "events": _finalize_events(events),
    }
    return aggregated


def _merge_counters(
    dest: dict[str, _CounterAccumulator],
    counters: Mapping[str, Mapping],
) -> None:
    for name, metric in counters.items():
        accumulator = dest.setdefault(name, _CounterAccumulator(description=metric.get("description", "")))
        samples = metric.get("samples", [])
        for sample in samples:
            labels = sample.get("labels") or {}
            key = _normalize_labels(labels)
            accumulator.samples[key] = accumulator.samples.get(key, 0.0) + float(sample.get("value", 0.0))
            accumulator.labels.setdefault(key, labels)


def _merge_histograms(
    dest: dict[str, _HistogramAccumulator],
    histograms: Mapping[str, Mapping],
) -> None:
    for name, metric in histograms.items():
        buckets = tuple(metric.get("buckets", ()))
        accumulator = dest.get(name)
        if accumulator is None:
            accumulator = _HistogramAccumulator(
                description=metric.get("description", ""),
                buckets=buckets,
            )
            dest[name] = accumulator

        samples = metric.get("samples", [])
        for sample in samples:
            bucket_entries = sample.get("buckets", [])
            if not bucket_entries:
                continue
            labels = sample.get("labels") or {}
            key = _normalize_labels(labels)
            counts = _bucket_entries_to_counts(bucket_entries)
            sample_acc = accumulator.samples.get(key)
            if sample_acc is None:
                sample_acc = _HistogramSampleAccumulator(
                    counts=[0.0] * len(counts),
                    labels=labels,
                )
                accumulator.samples[key] = sample_acc

            for idx, value in enumerate(counts):
                sample_acc.counts[idx] += float(value)
            sample_acc.sum += float(sample.get("sum", 0.0))
            sample_acc.count += float(sample.get("count", 0.0))


def _merge_events(
    dest: defaultdict[str, list],
    events: Mapping[str, list],
) -> None:
    for name, entries in events.items():
        if not isinstance(entries, list):
            continue
        dest[name].extend(entries)


def _finalize_counters(counters: Mapping[str, _CounterAccumulator]) -> dict:
    finalized: dict[str, dict] = {}
    for name, accumulator in counters.items():
        samples = []
        for key, value in accumulator.samples.items():
            samples.append(
                {
                    "labels": accumulator.labels.get(key, {}),
                    "value": value,
                }
            )
        finalized[name] = {
            "name": name,
            "description": accumulator.description,
            "type": "counter",
            "samples": samples,
        }
    return finalized


def _finalize_histograms(histograms: Mapping[str, _HistogramAccumulator]) -> dict:
    finalized: dict[str, dict] = {}
    for name, accumulator in histograms.items():
        bounds = list(accumulator.buckets) + ["+Inf"]
        samples = []
        for sample_acc in accumulator.samples.values():
            cumulative = 0.0
            bucket_exports = []
            for bound, inc in zip(bounds, sample_acc.counts):
                cumulative += inc
                bucket_exports.append({"le": bound, "count": cumulative})
            samples.append(
                {
                    "labels": sample_acc.labels,
                    "sum": sample_acc.sum,
                    "count": sample_acc.count,
                    "buckets": bucket_exports,
                }
            )
        finalized[name] = {
            "name": name,
            "description": accumulator.description,
            "buckets": list(accumulator.buckets),
            "type": "histogram",
            "samples": samples,
        }
    return finalized


def _finalize_events(events: Mapping[str, list]) -> dict[str, list]:
    finalized: dict[str, list] = {}
    for name, entries in events.items():
        if not isinstance(entries, list):
            continue
        finalized[name] = sorted(entries, key=lambda entry: entry.get("timestamp", 0))
    return finalized


def _bucket_entries_to_counts(bucket_entries: Sequence[Mapping[str, float]]) -> list[float]:
    counts: list[float] = []
    previous = 0.0
    for entry in bucket_entries:
        cumulative = float(entry.get("count", 0.0))
        counts.append(max(cumulative - previous, 0.0))
        previous = cumulative
    return counts
