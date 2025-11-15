import math

from ironswarm.metrics import aggregator
from ironswarm.metrics_snapshot import MetricsSnapshot


def _counter_metric(value, labels=None):
    return {
        "name": "ironswarm_http_requests_total",
        "description": "HTTP Requests",
        "type": "counter",
        "samples": [
            {
                "labels": labels or {},
                "value": value,
            }
        ],
    }


def _histogram_metric(buckets, counts, labels=None):
    cumulative = 0
    bucket_exports = []
    for boundary, inc in zip(list(buckets) + ["+Inf"], counts):
        cumulative += inc
        bucket_exports.append({"le": boundary, "count": cumulative})
    return {
        "name": "ironswarm_http_request_duration_seconds",
        "description": "Latency",
        "type": "histogram",
        "buckets": list(buckets),
        "samples": [
            {
                "labels": labels or {},
                "sum": sum(
                    boundary * inc
                    for boundary, inc in zip(list(buckets) + [1.0], counts)
                ),
                "count": sum(counts),
                "buckets": bucket_exports,
            }
        ],
    }


def _snapshot(node, timestamp, counter_value, histogram_counts, events):
    buckets = (0.1, 0.5)
    return MetricsSnapshot(
        node_identity=node,
        timestamp=timestamp,
        snapshot_data={
            "counters": {"ironswarm_http_requests_total": _counter_metric(counter_value)},
            "histograms": {
                "ironswarm_http_request_duration_seconds": _histogram_metric(
                    buckets,
                    histogram_counts,
                )
            },
            "events": events,
        },
    )


def test_cluster_snapshot_merges_all_metrics():
    snapshots = [
        _snapshot("node-a", 10, 10, [1, 1, 1], {"alerts": [{"node": "a"}]}),
        _snapshot("node-b", 20, 20, [0, 2, 3], {"alerts": [{"node": "b"}]}),
    ]

    result = aggregator.get_cluster_snapshot(snapshots)

    assert result["node_count"] == 2
    metric = result["counters"]["ironswarm_http_requests_total"]
    assert math.isclose(metric["samples"][0]["value"], 30)

    histogram = result["histograms"]["ironswarm_http_request_duration_seconds"]
    sample = histogram["samples"][0]
    bucket_counts = [entry["count"] for entry in sample["buckets"]]
    assert bucket_counts == [1, 4, 8]
    assert sample["count"] == 8
    assert result["events"]["alerts"] == [{"node": "a"}, {"node": "b"}]


def test_query_time_window_filters_snapshots():
    snapshots = [
        _snapshot("node-a", 10, 5, [1, 0, 0], {}),
        _snapshot("node-a", 20, 7, [0, 1, 0], {}),
        _snapshot("node-b", 30, 9, [0, 0, 1], {}),
    ]

    result = aggregator.query_time_window(
        snapshots,
        start_timestamp=15,
        end_timestamp=25,
    )

    metric = result["counters"]["ironswarm_http_requests_total"]
    assert metric["samples"][0]["value"] == 7
    assert result["node_count"] == 1


def test_get_per_node_snapshots_returns_latest_snapshot_per_node():
    snapshots = [
        _snapshot("node-a", 10, 5, [1, 0, 0], {}),
        _snapshot("node-a", 15, 9, [0, 1, 0], {}),
        _snapshot("node-b", 12, 3, [0, 0, 1], {}),
    ]

    per_node = aggregator.get_per_node_snapshots(snapshots)

    assert len(per_node) == 2
    node_a = next(item for item in per_node if item["node_identity"] == "node-a")
    assert node_a["timestamp"] == 15
    node_b = next(item for item in per_node if item["node_identity"] == "node-b")
    assert node_b["timestamp"] == 12
