from ironswarm.metrics.collector import MetricCollector


def test_counter_accumulates_with_labels():
    mc = MetricCollector()
    mc.inc("requests_total", labels={"method": "GET"})
    mc.inc("requests_total", amount=2, labels={"method": "GET"})
    mc.inc("requests_total", labels={"method": "POST"})

    snapshot = mc.snapshot()
    samples = snapshot["counters"]["requests_total"]["samples"]
    values = {sample["labels"]["method"]: sample["value"] for sample in samples}

    assert values["GET"] == 3
    assert values["POST"] == 1


def test_histogram_buckets_and_reset():
    mc = MetricCollector()
    buckets = (0.1, 1.0)
    mc.observe("latency_seconds", 0.05, buckets=buckets, labels={"path": "/"})
    mc.observe("latency_seconds", 0.5, buckets=buckets, labels={"path": "/"})
    mc.observe("latency_seconds", 2.0, buckets=buckets, labels={"path": "/"})

    snapshot = mc.snapshot()
    hist = snapshot["histograms"]["latency_seconds"]["samples"][0]

    # Buckets should be cumulative: <=0.1 ->1, <=1.0 ->2, +Inf ->3
    bucket_counts = [bucket["count"] for bucket in hist["buckets"]]
    assert bucket_counts[0] == 1
    assert bucket_counts[1] == 2
    assert bucket_counts[2] == 3
    assert hist["count"] == 3
    assert hist["sum"] == 2.55

    # Reset should clear internal state
    mc.reset()
    snapshot_after_reset = mc.snapshot()
    assert snapshot_after_reset["histograms"]["latency_seconds"]["samples"] == []


def test_snapshot_includes_events():
    mc = MetricCollector()
    mc.record_event("http_request", {"timestamp": 1.23, "value": 1})

    snapshot = mc.snapshot()
    assert "http_request" in snapshot["events"]
    assert snapshot["events"]["http_request"][0]["timestamp"] == 1.23

    mc.reset()
    assert mc.snapshot()["events"].get("http_request", []) == []
