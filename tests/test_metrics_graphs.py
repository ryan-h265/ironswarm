import importlib

import pytest

from ironswarm.metrics.graphs import (
    _latency_timeseries,
    _stacked_series_data,
    generate_graphs,
)

HAVE_MPL = importlib.util.find_spec("matplotlib") is not None


def _snapshot():
    base_time = 1_700_000_000
    events = []
    for idx in range(5):
        events.append(
            {
                "timestamp": base_time + idx,
                "duration": 0.1 * (idx + 1),
                "labels": {
                    "method": "GET" if idx % 2 == 0 else "POST",
                    "host": "api.example.com",
                    "path": "/health" if idx % 2 == 0 else "/login",
                    "status": "200" if idx != 3 else "500",
                },
            }
        )
    return {
        "events": {
            "http_request": events,
        }
    }


def test_latency_timeseries_percentiles():
    snapshot = _snapshot()
    series = _latency_timeseries(snapshot["events"]["http_request"], bin_seconds=1)

    assert len(series) == 5
    # First bucket should have single duration 0.1
    assert series[0]["p50"] == pytest.approx(0.1)
    # Last bucket should have duration 0.5
    assert series[-1]["p99"] == pytest.approx(0.5)


def test_stacked_series_data_groups_by_endpoint():
    snapshot = _snapshot()
    times, labels, series = _stacked_series_data(
        snapshot["events"]["http_request"],
        bin_seconds=1,
        limit=2,
    )
    assert len(labels) == 2
    assert len(series) == 2
    assert len(times) == 5
    # Sum of all stacked values equals total events
    total = sum(sum(values) for values in zip(*series, strict=False))
    assert total == len(snapshot["events"]["http_request"])


@pytest.mark.skipif(not HAVE_MPL, reason="matplotlib not installed")
def test_generate_graphs_writes_files(tmp_path):
    snapshot = _snapshot()
    files = generate_graphs(snapshot, tmp_path, limit=5, bin_seconds=1)

    assert len(files) >= 2
    for file in files:
        assert file.exists()
