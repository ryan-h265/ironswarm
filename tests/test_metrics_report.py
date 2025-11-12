from ironswarm.metrics.report import format_report, summarize_snapshot


def _sample_snapshot():
    return {
        "counters": {
            "ironswarm_journey_executions_total": {
                "samples": [
                    {"labels": {"scenario": "smoke", "journey": "login"}, "value": 10},
                    {"labels": {"scenario": "smoke", "journey": "search"}, "value": 5},
                ]
            },
            "ironswarm_journey_failures_total": {
                "samples": [
                    {"labels": {"scenario": "smoke", "journey": "login", "error": "Timeout"}, "value": 2}
                ]
            },
            "ironswarm_http_requests_total": {
                "samples": [
                    {
                        "labels": {
                            "method": "GET",
                            "host": "api.example.com",
                            "path": "/health",
                        },
                        "value": 50,
                    },
                    {
                        "labels": {
                            "method": "POST",
                            "host": "api.example.com",
                            "path": "/login",
                        },
                        "value": 20,
                    },
                ]
            },
            "ironswarm_http_errors_total": {
                "samples": [
                    {
                        "labels": {
                            "method": "POST",
                            "host": "api.example.com",
                            "path": "/login",
                        },
                        "value": 3,
                    }
                ]
            },
        },
        "histograms": {
            "ironswarm_http_request_duration_seconds": {
                "samples": [
                    {
                        "labels": {
                            "method": "POST",
                            "host": "api.example.com",
                            "path": "/login",
                        },
                        "count": 20,
                        "sum": 4.0,
                        "buckets": [],
                    },
                    {
                        "labels": {
                            "method": "GET",
                            "host": "api.example.com",
                            "path": "/health",
                        },
                        "count": 50,
                        "sum": 5.0,
                        "buckets": [],
                    },
                ]
            }
        },
    }


def test_summarize_snapshot_returns_human_readable_lines():
    snapshot = _sample_snapshot()
    lines = summarize_snapshot(snapshot, limit=2)

    assert any("Journeys" in line for line in lines)
    assert any("HTTP" in line for line in lines)
    assert any("Top journeys" in line for line in lines)
    assert any("Slowest HTTP endpoints" in line for line in lines)


def test_format_report_contains_header_and_summary():
    snapshot = _sample_snapshot()
    report = format_report(snapshot, limit=1)

    assert "Ironswarm Metrics Report" in report
    assert "Journeys:" in report
