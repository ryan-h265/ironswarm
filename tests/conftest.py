import json
import os
from pathlib import Path

import pytest

from ironswarm.metrics.collector import collector
from ironswarm.metrics.report import summarize_snapshot

SNAPSHOT_ENV_VAR = "IRONSWARM_METRICS_SNAPSHOT"
DEFAULT_SNAPSHOT_PATH = "metrics_snapshot.json"


def _snapshot_path() -> str | None:
    raw = os.environ.get(SNAPSHOT_ENV_VAR)
    if raw is None:
        return DEFAULT_SNAPSHOT_PATH
    normalized = raw.strip().lower()
    if normalized in {"", "0", "false", "off"}:
        return None
    return raw


def pytest_sessionstart(session):
    """Ensure metrics collector starts from a clean slate each run."""
    collector.reset()


@pytest.fixture
def metrics_collector():
    """
    Fixture for tests that need a clean collector state.

    Resets the global collector before and after yielding to avoid cross-test coupling.
    """
    collector.reset()
    yield collector
    collector.reset()


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Write snapshot to disk and display a short summary after tests finish."""
    snapshot = collector.snapshot()
    summary_lines = summarize_snapshot(snapshot)
    if summary_lines:
        terminalreporter.section("Ironswarm Metrics Summary", sep="=")
        for line in summary_lines:
            terminalreporter.write_line(line)

    path = _snapshot_path()
    if path:
        path_obj = Path(path)
        if path_obj.parent:
            path_obj.parent.mkdir(parents=True, exist_ok=True)
        path_obj.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        terminalreporter.write_line(f"Ironswarm metrics snapshot written to {path_obj}")
