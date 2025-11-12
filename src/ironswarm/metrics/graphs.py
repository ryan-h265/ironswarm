from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

try:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover
    matplotlib = None
    plt = None
    mdates = None

import math
from collections import Counter, defaultdict
from datetime import datetime

from ironswarm.metrics.report import load_snapshot

Snapshot = dict[str, Any]


def _require_matplotlib() -> None:
    if plt is None:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "matplotlib is required for graph generation. "
            "Install via `pip install ironswarm[graphs]`."
        )


def _endpoint_label(labels: dict[str, str]) -> str:
    host = labels.get("host", "")
    path = labels.get("path", "/") or "/"
    method = labels.get("method", "GET")
    return f"{method} {host}{path}"


def _http_events(snapshot: Snapshot) -> list[dict[str, Any]]:
    return snapshot.get("events", {}).get("http_request", [])


def _bin_timestamp(timestamp: float, bin_seconds: float) -> float:
    return math.floor(timestamp / bin_seconds) * bin_seconds


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    index = quantile * (len(values) - 1)
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return values[int(index)]
    lower_value = values[lower]
    upper_value = values[upper]
    fraction = index - lower
    return lower_value + (upper_value - lower_value) * fraction


def _latency_timeseries(events: list[dict[str, Any]], bin_seconds: float) -> list[dict[str, Any]]:
    buckets: dict[float, list[float]] = defaultdict(list)
    for event in events:
        timestamp = event.get("timestamp")
        duration = event.get("duration")
        if timestamp is None or duration is None:
            continue
        bucket = _bin_timestamp(timestamp, bin_seconds)
        buckets[bucket].append(duration)

    timeseries: list[dict[str, Any]] = []
    for bucket in sorted(buckets.keys()):
        durations = sorted(buckets[bucket])
        timeseries.append(
            {
                "time": bucket,
                "p50": _percentile(durations, 0.5),
                "p95": _percentile(durations, 0.95),
                "p99": _percentile(durations, 0.99),
            }
        )
    return timeseries


def _plot_latency_timeseries(series: list[dict[str, Any]], output: Path) -> None:
    _require_matplotlib()
    if not series:
        return
    times = [datetime.fromtimestamp(entry["time"]) for entry in series]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(times, [entry["p50"] * 1000 for entry in series], label="P50", marker="o")
    ax.plot(times, [entry["p95"] * 1000 for entry in series], label="P95", marker="o")
    ax.plot(times, [entry["p99"] * 1000 for entry in series], label="P99", marker="o")
    ax.set_ylabel("Latency (ms)")
    ax.set_title("HTTP Latency Over Time")
    ax.grid(True, axis="y", linestyle="--", alpha=0.4)
    ax.legend()
    if mdates:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output, dpi=150)
    plt.close(fig)


def _stacked_series_data(
    events: list[dict[str, Any]],
    bin_seconds: float,
    limit: int,
    predicate: Callable[[dict[str, Any]], bool] | None = None,
) -> tuple[list[datetime], list[str], list[list[float]]]:
    buckets: dict[float, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    totals: Counter[str] = Counter()

    for event in events:
        if predicate and not predicate(event):
            continue
        timestamp = event.get("timestamp")
        if timestamp is None:
            continue
        labels = event.get("labels", {})
        label = _endpoint_label(labels)
        bucket = _bin_timestamp(timestamp, bin_seconds)
        buckets[bucket][label] += 1
        totals[label] += 1

    if not buckets:
        return ([], [], [])

    top_labels = [label for label, _ in totals.most_common(limit)]
    times = sorted(buckets.keys())
    datetime_axis = [datetime.fromtimestamp(ts) for ts in times]

    series: list[list[float]] = []
    for label in top_labels:
        counts = []
        for ts in times:
            value = buckets[ts].get(label, 0.0)
            counts.append(value / bin_seconds)
        series.append(counts)

    return (datetime_axis, top_labels, series)


def _plot_stack(
    times: list[datetime],
    labels: list[str],
    series: list[list[float]],
    output: Path,
    title: str,
    ylabel: str,
) -> None:
    _require_matplotlib()
    if not times or not labels:
        return
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.stackplot(times, *series, labels=labels)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, axis="y", linestyle="--", alpha=0.4)
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1))
    if mdates:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _counter_samples(snapshot: Snapshot, metric_name: str) -> list[dict[str, Any]]:
    metric = snapshot.get("counters", {}).get(metric_name)
    if not metric:
        return []
    return metric.get("samples", [])


def _collect_counter_series(samples: list[dict[str, Any]], limit: int) -> list[tuple[str, float]]:
    aggregated: dict[str, float] = {}
    for sample in samples:
        label = _endpoint_label(sample.get("labels", {}))
        aggregated[label] = aggregated.get(label, 0.0) + float(sample.get("value", 0))
    sorted_items = sorted(aggregated.items(), key=lambda kv: kv[1], reverse=True)
    return sorted_items[:limit]


def _percentile_from_buckets(
    buckets: list[dict[str, Any]], percentile: float, total_count: int
) -> float:
    if total_count == 0:
        return 0.0
    threshold = total_count * percentile
    for bucket in buckets:
        boundary = bucket.get("le")
        boundary_value = float("inf") if boundary == "+Inf" else float(boundary)
        if bucket.get("count", 0) >= threshold:
            return boundary_value
    return float("inf")


def _latency_stats(snapshot: Snapshot, limit: int) -> list[dict[str, Any]]:
    histogram = snapshot.get("histograms", {}).get(
        "ironswarm_http_request_duration_seconds"
    )
    if not histogram:
        return []

    stats: list[dict[str, Any]] = []
    for sample in histogram.get("samples", []):
        count = sample.get("count", 0)
        if not count:
            continue
        buckets = sample.get("buckets", [])
        stats.append(
            {
                "label": _endpoint_label(sample.get("labels", {})),
                "count": count,
                "avg": sample.get("sum", 0.0) / count,
                "p50": _percentile_from_buckets(buckets, 0.5, count),
                "p95": _percentile_from_buckets(buckets, 0.95, count),
                "p99": _percentile_from_buckets(buckets, 0.99, count),
            }
        )

    stats.sort(key=lambda item: item["avg"], reverse=True)
    return stats[:limit]


def _plot_latency(stats: list[dict[str, Any]], output: Path) -> None:
    _require_matplotlib()
    labels = [item["label"] for item in stats]
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.2), 4))
    ax.plot(x, [item["p50"] * 1000 for item in stats], label="P50", marker="o")
    ax.plot(x, [item["p95"] * 1000 for item in stats], label="P95", marker="o")
    ax.plot(x, [item["p99"] * 1000 for item in stats], label="P99", marker="o")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel("Latency (ms)")
    ax.set_title("HTTP Latency Percentiles")
    ax.grid(True, axis="y", linestyle="--", alpha=0.4)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=150)
    plt.close(fig)


def _plot_bar(
    data: list[tuple[str, float]],
    output: Path,
    title: str,
    ylabel: str,
    color: str,
) -> None:
    _require_matplotlib()
    labels = [label for label, _ in data]
    values = [value for _, value in data]
    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.2), 4))
    ax.bar(range(len(labels)), values, color=color)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    fig.savefig(output, dpi=150)
    plt.close(fig)


def generate_graphs(
    snapshot: Snapshot,
    output_dir: str | Path,
    limit: int = 10,
    bin_seconds: float = 1.0,
) -> list[Path]:
    _require_matplotlib()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    events = _http_events(snapshot)
    if events:
        latency_series = _latency_timeseries(events, bin_seconds)
        if latency_series:
            path = output_path / "latency.png"
            _plot_latency_timeseries(latency_series, path)
            generated.append(path)

        throughput_times, throughput_labels, throughput_series = _stacked_series_data(
            events,
            bin_seconds,
            limit,
        )
        if throughput_times and throughput_labels:
            path = output_path / "throughput.png"
            _plot_stack(
                throughput_times,
                throughput_labels,
                throughput_series,
                path,
                title="HTTP Throughput (requests/sec)",
                ylabel="Requests / sec",
            )
            generated.append(path)

        error_times, error_labels, error_series = _stacked_series_data(
            events,
            bin_seconds,
            limit,
            predicate=lambda evt: int(evt.get("labels", {}).get("status", 0)) >= 400,
        )
        if error_times and error_labels:
            path = output_path / "errors.png"
            _plot_stack(
                error_times,
                error_labels,
                error_series,
                path,
                title="HTTP Errors (per sec)",
                ylabel="Errors / sec",
            )
            generated.append(path)

        return generated
    raise RuntimeError(
        "Snapshot missing HTTP request events. "
        "Please re-run your scenario with a newer ironswarm version that records "
        "per-request events."
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate latency/throughput/error graphs from a metrics snapshot."
    )
    parser.add_argument(
        "snapshot",
        nargs="?",
        default="metrics_snapshot.json",
        help="Path to metrics snapshot JSON (default: metrics_snapshot.json)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default="metrics_graphs",
        help="Directory to write PNG graphs (default: metrics_graphs)",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=10,
        help="Maximum number of endpoints to plot per graph (default: 10)",
    )
    parser.add_argument(
        "--bin-size",
        type=float,
        default=1.0,
        help="Time bucket size in seconds for throughput/latency graphs (default: 1.0)",
    )

    args = parser.parse_args(argv)
    snapshot = load_snapshot(args.snapshot)
    try:
        files = generate_graphs(
            snapshot,
            args.output_dir,
            limit=args.limit,
            bin_seconds=args.bin_size,
        )
    except RuntimeError as exc:
        parser.exit(f"{exc}\n")
    for file in files:
        print(f"Generated {file}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
