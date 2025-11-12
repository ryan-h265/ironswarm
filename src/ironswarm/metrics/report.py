from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

Snapshot = dict[str, Any]


def _counter_total(snapshot: Snapshot, metric_name: str) -> float:
    metric = snapshot.get("counters", {}).get(metric_name)
    if not metric:
        return 0.0
    return sum(sample.get("value", 0) for sample in metric.get("samples", []))


def _group_counter_samples(
    snapshot: Snapshot, metric_name: str, keys: Sequence[str]
) -> list[tuple[float, dict[str, str]]]:
    metric = snapshot.get("counters", {}).get(metric_name)
    if not metric:
        return []
    totals: dict[tuple[str, ...], float] = {}
    label_cache: dict[tuple[str, ...], dict[str, str]] = {}
    for sample in metric.get("samples", []):
        labels = sample.get("labels", {})
        key = tuple(labels.get(k, "unknown") for k in keys)
        totals[key] = totals.get(key, 0.0) + float(sample.get("value", 0))
        label_cache[key] = {k: labels.get(k, "unknown") for k in keys}
    sorted_totals = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    return [(value, label_cache[key]) for key, value in sorted_totals]


def _histogram_samples(snapshot: Snapshot, metric_name: str) -> list[dict[str, Any]]:
    metric = snapshot.get("histograms", {}).get(metric_name)
    if not metric:
        return []
    return [
        sample
        for sample in metric.get("samples", [])
        if sample.get("count", 0) > 0
    ]


def summarize_snapshot(snapshot: Snapshot, limit: int = 5) -> list[str]:
    """
    Build short human-readable summary lines for terminal output.
    """
    lines: list[str] = []

    total_journeys = _counter_total(snapshot, "ironswarm_journey_executions_total")
    journey_failures = _counter_total(snapshot, "ironswarm_journey_failures_total")
    if total_journeys or journey_failures:
        failure_rate = (
            (journey_failures / total_journeys) * 100 if total_journeys else 0.0
        )
        lines.append(
            f"Journeys: {int(total_journeys)} executed, "
            f"{int(journey_failures)} failures ({failure_rate:.1f}% fail)"
        )
        top_journeys = _group_counter_samples(
            snapshot, "ironswarm_journey_executions_total", ("scenario", "journey")
        )
        if top_journeys:
            lines.append("Top journeys:")
            for value, labels in top_journeys[:limit]:
                lines.append(
                    f"  - {labels['scenario']}/{labels['journey']}: {int(value)} runs"
                )

    total_http = _counter_total(snapshot, "ironswarm_http_requests_total")
    http_errors = _counter_total(snapshot, "ironswarm_http_errors_total")
    if total_http or http_errors:
        error_rate = (http_errors / total_http * 100) if total_http else 0.0
        lines.append(
            f"HTTP: {int(total_http)} requests, {int(http_errors)} errors "
            f"({error_rate:.1f}% error rate)"
        )
        top_http = _group_counter_samples(
            snapshot,
            "ironswarm_http_requests_total",
            ("method", "host", "path"),
        )
        if top_http:
            lines.append("Top HTTP targets:")
            for value, labels in top_http[:limit]:
                host = labels.get("host", "")
                path = labels.get("path", "/")
                lines.append(
                    f"  - {labels['method']} {host}{path}: {int(value)} requests"
                )

        latency_samples = _histogram_samples(
            snapshot, "ironswarm_http_request_duration_seconds"
        )
        if latency_samples:
            slowest = sorted(
                latency_samples,
                key=lambda sample: sample["sum"] / sample["count"],
                reverse=True,
            )[:limit]
            lines.append("Slowest HTTP endpoints (avg duration):")
            for sample in slowest:
                labels = sample.get("labels", {})
                avg = sample["sum"] / sample["count"]
                host = labels.get("host", "")
                path = labels.get("path", "/")
                lines.append(
                    f"  - {labels.get('method', 'GET')} {host}{path}: "
                    f"{avg * 1000:.1f} ms over {int(sample['count'])} samples"
                )

    return lines


def format_report(snapshot: Snapshot, limit: int = 5) -> str:
    lines = ["Ironswarm Metrics Report", "=" * 27, ""]
    summary_lines = summarize_snapshot(snapshot, limit=limit)
    if summary_lines:
        lines.extend(summary_lines)
    else:
        lines.append("No metrics recorded.")
    return "\n".join(lines)


def load_snapshot(path: str | Path) -> Snapshot:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate human-readable report from an Ironswarm metrics snapshot."
    )
    parser.add_argument(
        "snapshot",
        nargs="?",
        default="metrics_snapshot.json",
        help="Path to metrics snapshot JSON (default: metrics_snapshot.json)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Optional path to write the formatted report (defaults to stdout).",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=5,
        help="Maximum number of entries per section (default: 5).",
    )

    args = parser.parse_args(argv)
    snapshot = load_snapshot(args.snapshot)
    report = format_report(snapshot, limit=args.limit)

    if args.output:
        output_path = Path(args.output)
        if output_path.parent:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
    else:
        print(report)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
