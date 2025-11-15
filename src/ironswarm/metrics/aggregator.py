"""
Metrics aggregation utilities for combining snapshots across cluster nodes.

Provides functions to merge metrics from multiple nodes into cluster-wide views,
supporting counters, histograms, and event streams.
"""

from collections import defaultdict
from typing import Any

from ironswarm.metrics_snapshot import MetricsSnapshot


def _aggregate_counter_samples(samples_list: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """
    Aggregate counter samples from multiple nodes.

    Sums values for matching label sets across all nodes.

    Args:
        samples_list: List of sample lists, one per node

    Returns:
        Aggregated samples with summed values
    """
    # Group by labels, sum values
    label_to_value: dict[tuple[tuple[str, Any], ...], float] = defaultdict(float)

    for samples in samples_list:
        for sample in samples:
            # Convert labels dict to sorted tuple for hashing
            labels = sample.get("labels", {})
            label_key = tuple(sorted(labels.items()))
            label_to_value[label_key] += sample.get("value", 0)

    # Convert back to list format
    aggregated = []
    for label_key, value in label_to_value.items():
        aggregated.append({
            "labels": dict(label_key),
            "value": value,
        })

    return aggregated


def _aggregate_histogram_samples(samples_list: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """
    Aggregate histogram samples from multiple nodes.

    Combines buckets, sums counts, and sums totals for matching label sets.

    Args:
        samples_list: List of sample lists, one per node

    Returns:
        Aggregated samples with combined histograms
    """
    # Group by labels
    label_to_histogram: dict[tuple[tuple[str, Any], ...], dict[str, Any]] = defaultdict(
        lambda: {"buckets": defaultdict(int), "count": 0, "sum": 0.0}
    )

    for samples in samples_list:
        for sample in samples:
            labels = sample.get("labels", {})
            label_key = tuple(sorted(labels.items()))
            histogram = label_to_histogram[label_key]

            # Merge buckets
            for bucket in sample.get("buckets", []):
                le = bucket.get("le")
                count = bucket.get("count", 0)
                histogram["buckets"][le] += count

            # Sum totals
            histogram["count"] += sample.get("count", 0)
            histogram["sum"] += sample.get("sum", 0.0)

    # Convert back to list format
    aggregated = []
    for label_key, histogram in label_to_histogram.items():
        # Convert buckets dict back to list
        buckets = [
            {"le": le, "count": count}
            for le, count in sorted(histogram["buckets"].items())
        ]

        aggregated.append({
            "labels": dict(label_key),
            "buckets": buckets,
            "count": histogram["count"],
            "sum": histogram["sum"],
        })

    return aggregated


def _aggregate_events(events_list: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """
    Aggregate event streams from multiple nodes.

    Concatenates events and sorts by timestamp.

    Args:
        events_list: List of event lists, one per node

    Returns:
        Merged and sorted event list
    """
    all_events = []
    for events in events_list:
        all_events.extend(events)

    # Sort by timestamp
    all_events.sort(key=lambda e: e.get("timestamp", 0))

    return all_events


def aggregate_snapshots(snapshots: list[MetricsSnapshot]) -> dict[str, Any]:
    """
    Aggregate multiple node snapshots into a single cluster-wide snapshot.

    Merges counters (sum), histograms (combine), and events (concatenate).

    Args:
        snapshots: List of MetricsSnapshot objects to aggregate

    Returns:
        Aggregated snapshot dictionary with cluster-wide metrics
    """
    if not snapshots:
        return {
            "timestamp": 0,
            "node_count": 0,
            "counters": {},
            "histograms": {},
            "events": {},
        }

    # Collect data by metric name
    counters_by_name: dict[str, list[list[dict[str, Any]]]] = defaultdict(list)
    histograms_by_name: dict[str, list[list[dict[str, Any]]]] = defaultdict(list)
    events_by_name: dict[str, list[list[dict[str, Any]]]] = defaultdict(list)

    for snapshot in snapshots:
        data = snapshot.snapshot_data

        # Collect counters
        for counter_name, counter_data in data.get("counters", {}).items():
            samples = counter_data.get("samples", [])
            counters_by_name[counter_name].append(samples)

        # Collect histograms
        for hist_name, hist_data in data.get("histograms", {}).items():
            samples = hist_data.get("samples", [])
            histograms_by_name[hist_name].append(samples)

        # Collect events
        for event_name, event_list in data.get("events", {}).items():
            events_by_name[event_name].append(event_list)

    # Aggregate each metric
    aggregated_counters = {}
    for name, samples_list in counters_by_name.items():
        aggregated_counters[name] = {
            "samples": _aggregate_counter_samples(samples_list)
        }

    aggregated_histograms = {}
    for name, samples_list in histograms_by_name.items():
        aggregated_histograms[name] = {
            "samples": _aggregate_histogram_samples(samples_list)
        }

    aggregated_events = {}
    for name, events_list in events_by_name.items():
        aggregated_events[name] = _aggregate_events(events_list)

    # Use latest timestamp
    latest_timestamp = max(s.timestamp for s in snapshots)

    return {
        "timestamp": latest_timestamp,
        "node_count": len(set(s.node_identity for s in snapshots)),
        "counters": aggregated_counters,
        "histograms": aggregated_histograms,
        "events": aggregated_events,
    }


def query_time_window(
    snapshots: list[MetricsSnapshot],
    start_timestamp: int | None = None,
    end_timestamp: int | None = None,
) -> dict[str, Any]:
    """
    Get aggregated metrics for a specific time window.

    Args:
        snapshots: List of all available snapshots
        start_timestamp: Start of time window (inclusive), or None for no lower bound
        end_timestamp: End of time window (inclusive), or None for no upper bound

    Returns:
        Aggregated snapshot for the time window
    """
    filtered = []
    for snapshot in snapshots:
        if start_timestamp is not None and snapshot.timestamp < start_timestamp:
            continue
        if end_timestamp is not None and snapshot.timestamp > end_timestamp:
            continue
        filtered.append(snapshot)

    return aggregate_snapshots(filtered)


def get_cluster_snapshot(snapshots: list[MetricsSnapshot]) -> dict[str, Any]:
    """
    Get current cluster-wide metrics from all available snapshots.

    Args:
        snapshots: List of all available snapshots

    Returns:
        Aggregated snapshot representing current cluster state
    """
    return aggregate_snapshots(snapshots)


def get_per_node_snapshots(snapshots: list[MetricsSnapshot]) -> dict[str, dict[str, Any]]:
    """
    Get latest snapshot for each node.

    Args:
        snapshots: List of all available snapshots

    Returns:
        Dictionary mapping node_identity to latest snapshot data
    """
    node_to_latest: dict[str, MetricsSnapshot] = {}

    for snapshot in snapshots:
        current = node_to_latest.get(snapshot.node_identity)
        if current is None or snapshot.timestamp > current.timestamp:
            node_to_latest[snapshot.node_identity] = snapshot

    return {
        node_id: snapshot.snapshot_data
        for node_id, snapshot in node_to_latest.items()
    }


def get_time_series(
    snapshots: list[MetricsSnapshot],
    metric_name: str,
    metric_type: str = "counter",
) -> list[dict[str, Any]]:
    """
    Get time-series data for a specific metric across all nodes.

    Args:
        snapshots: List of snapshots to extract from
        metric_name: Name of the metric to extract
        metric_type: Type of metric ("counter", "histogram", or "event")

    Returns:
        List of data points sorted by timestamp
    """
    time_series = []

    for snapshot in sorted(snapshots, key=lambda s: s.timestamp):
        data = snapshot.snapshot_data

        if metric_type == "counter":
            counter_data = data.get("counters", {}).get(metric_name)
            if counter_data:
                time_series.append({
                    "timestamp": snapshot.timestamp,
                    "node_identity": snapshot.node_identity,
                    "samples": counter_data.get("samples", []),
                })

        elif metric_type == "histogram":
            hist_data = data.get("histograms", {}).get(metric_name)
            if hist_data:
                time_series.append({
                    "timestamp": snapshot.timestamp,
                    "node_identity": snapshot.node_identity,
                    "samples": hist_data.get("samples", []),
                })

        elif metric_type == "event":
            events = data.get("events", {}).get(metric_name, [])
            if events:
                time_series.append({
                    "timestamp": snapshot.timestamp,
                    "node_identity": snapshot.node_identity,
                    "events": events,
                })

    return time_series
