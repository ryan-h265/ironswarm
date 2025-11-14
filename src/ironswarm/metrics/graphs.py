from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib import colors as mcolors
    from matplotlib.patches import PathPatch
    from cycler import cycler
    import numpy as np
except ImportError:  # pragma: no cover
    matplotlib = None
    plt = None
    mdates = None
    cycler = None
    mcolors = None
    PathPatch = None
    np = None

import math
from collections import Counter, defaultdict
from datetime import datetime

from ironswarm.metrics.report import load_snapshot

Snapshot = dict[str, Any]


_ACCENT_COLORS = [
    "#6EE7B7",
    "#22D3EE",
    "#3B82F6",
    "#A855F7",
    "#F472B6",
    "#FBBF24",
]
_STACK_COLORS = [
    "#0E7490",
    "#2563EB",
    "#7C3AED",
    "#C026D3",
    "#FB7185",
    "#F59E0B",
    "#84CC16",
    "#14B8A6",
]
_BACKGROUND_COLOR = "#070b12"
_PANEL_COLOR = "#0e1524"
_PANEL_GRADIENT_TOP = "#111a2f"
_PANEL_GRADIENT_BOTTOM = "#05070f"
_TEXT_COLOR = "#f4f5f7"
_GRID_COLOR = "#1e2636"
_P50_COLOR = "#9FE2BF"
_P95_COLOR = "#FFDD57"
_P99_COLOR = "#FF6B6B"


def _empty_snapshot() -> Snapshot:
    return {
        "events": {},
        "counters": {},
        "histograms": {},
    }


def _load_snapshot_source(source: str | Path) -> Snapshot:
    source_path = Path(source)
    if source_path.is_dir():
        files = sorted(p for p in source_path.rglob("*.json") if p.is_file())
        if not files:
            raise RuntimeError(f"No JSON snapshots found in directory {source_path}")
        aggregated = _empty_snapshot()
        for file in files:
            data = load_snapshot(file)
            _merge_snapshot(aggregated, data)
        return aggregated
    if not source_path.exists():
        raise RuntimeError(f"Snapshot path {source_path} does not exist")
    return load_snapshot(source_path)


def _merge_snapshot(target: Snapshot, data: Snapshot) -> None:
    _merge_events(target, data)
    _merge_counters(target, data)
    _merge_histograms(target, data)


def _merge_events(target: Snapshot, data: Snapshot) -> None:
    target_events = target.setdefault("events", {})
    for name, events in data.get("events", {}).items():
        target_events.setdefault(name, []).extend(events)


def _merge_counters(target: Snapshot, data: Snapshot) -> None:
    target_counters = target.setdefault("counters", {})
    for metric, payload in data.get("counters", {}).items():
        samples = payload.get("samples", [])
        target_metric = target_counters.setdefault(metric, {"samples": []})
        target_metric.setdefault("samples", []).extend(samples)


def _merge_histograms(target: Snapshot, data: Snapshot) -> None:
    target_hists = target.setdefault("histograms", {})
    for metric, payload in data.get("histograms", {}).items():
        target_metric = target_hists.setdefault(metric, {"samples": []})
        merged = _merge_histogram_samples(target_metric.get("samples", []), payload.get("samples", []))
        target_metric["samples"] = merged


def _histogram_key(sample: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    labels = sample.get("labels", {})
    return tuple(sorted((str(key), str(value)) for key, value in labels.items()))


def _merge_histogram_samples(
    existing_samples: list[dict[str, Any]],
    new_samples: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    index: dict[tuple[tuple[str, str], ...], dict[str, Any]] = {
        _histogram_key(sample): sample for sample in existing_samples
    }
    for sample in new_samples:
        key = _histogram_key(sample)
        if key in index:
            target_sample = index[key]
            target_sample["count"] = target_sample.get("count", 0) + sample.get("count", 0)
            target_sample["sum"] = target_sample.get("sum", 0.0) + sample.get("sum", 0.0)
            target_sample["buckets"] = _merge_histogram_buckets(
                target_sample.get("buckets", []), sample.get("buckets", [])
            )
        else:
            sample_copy = deepcopy(sample)
            existing_samples.append(sample_copy)
            index[key] = sample_copy
    return existing_samples


def _merge_histogram_buckets(
    existing_buckets: list[dict[str, Any]],
    new_buckets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    bucket_map: dict[str, dict[str, Any]] = {
        bucket.get("le"): bucket for bucket in existing_buckets
    }
    for bucket in new_buckets:
        key = bucket.get("le")
        entry = bucket_map.setdefault(key, {"le": key, "count": 0})
        entry["count"] = entry.get("count", 0) + bucket.get("count", 0)

    def sort_key(bucket: dict[str, Any]) -> float:
        boundary = bucket.get("le")
        if boundary == "+Inf":
            return float("inf")
        try:
            return float(boundary)
        except (TypeError, ValueError):
            return float("inf")

    return sorted(bucket_map.values(), key=sort_key)


def _configure_theme() -> None:
    if plt is None or matplotlib is None:
        return
    rc_updates = {
        "figure.facecolor": _BACKGROUND_COLOR,
        "axes.facecolor": _PANEL_COLOR,
        "axes.edgecolor": _PANEL_COLOR,
        "axes.labelcolor": _TEXT_COLOR,
        "axes.titleweight": "semibold",
        "axes.titlesize": 16,
        "axes.titlecolor": _TEXT_COLOR,
        "xtick.color": _TEXT_COLOR,
        "ytick.color": _TEXT_COLOR,
        "grid.color": _GRID_COLOR,
        "grid.linestyle": "--",
        "grid.linewidth": 0.8,
        "axes.grid": True,
        "font.size": 11,
    }
    matplotlib.rcParams.update(rc_updates)
    if cycler is not None:
        matplotlib.rcParams["axes.prop_cycle"] = cycler(color=_ACCENT_COLORS)


def _theme_figure(figsize: tuple[float, float]) -> tuple[Any, Any]:
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(_BACKGROUND_COLOR)
    ax.set_facecolor(_PANEL_COLOR)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(axis="both", which="both", labelsize=10)
    return fig, ax


def _restyle_legend(legend: Any | None) -> None:
    if legend is None:
        return
    frame = legend.get_frame()
    if frame is not None:
        frame.set_facecolor(_PANEL_COLOR)
        frame.set_edgecolor(_PANEL_COLOR)
    for text in legend.get_texts():
        text.set_color(_TEXT_COLOR)
    title = legend.get_title()
    if title:
        title.set_color(_TEXT_COLOR)


def _blend_colors(color: str, target: str, ratio: float) -> str:
    if mcolors is None:
        return color
    ratio = max(0.0, min(1.0, ratio))
    base_rgb = mcolors.to_rgb(color)
    target_rgb = mcolors.to_rgb(target)
    blended = tuple((1 - ratio) * base + ratio * target for base, target in zip(base_rgb, target_rgb))
    return mcolors.to_hex(blended)


def _apply_background_gradient(
    ax: Any,
    start: str | None = None,
    end: str | None = None,
    alpha: float = 0.55,
) -> None:
    if plt is None or mcolors is None:
        return
    start_color = start or _PANEL_GRADIENT_TOP
    end_color = end or _PANEL_GRADIENT_BOTTOM
    gradient = [[0, 0], [1, 1]]
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "panel-gradient",
        [start_color, end_color],
    )
    image = ax.imshow(
        gradient,
        aspect="auto",
        cmap=cmap,
        interpolation="bicubic",
        extent=[x0, x1, y0, y1],
        alpha=alpha,
        zorder=-10,
        origin="lower",
        clip_on=False,
    )
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)


def _enhance_stackplot(ax: Any, collections: Sequence[Any], palette: Sequence[str]) -> None:
    if PathPatch is None:
        return
    for collection, color in zip(collections, palette):
        face_color = _blend_colors(color, _BACKGROUND_COLOR, 0.35)
        collection.set_facecolor(face_color)
        collection.set_edgecolor(_blend_colors(color, _BACKGROUND_COLOR, 0.65))
        collection.set_alpha(0.65)
        for path in collection.get_paths():
            patch = PathPatch(path, facecolor="none", edgecolor="none", transform=ax.transData)
            patch.set_zorder(collection.get_zorder() + 0.01)
            ax.add_patch(patch)
            _add_gradient_to_patch(ax, patch, color, orientation="vertical")


def _patch_vertices_in_data(patch: Any) -> np.ndarray | None:
    if patch is None or not hasattr(patch, "get_path"):
        return None
    path = patch.get_path()
    transform_getter = getattr(patch, "get_transform", None)
    axes = getattr(patch, "axes", None)
    if path is None or transform_getter is None or axes is None:
        return None
    transform = transform_getter()
    if transform is None:
        return None
    vertices = transform.transform(path.vertices)
    try:
        vertices = axes.transData.inverted().transform(vertices)
    except Exception:  # pragma: no cover - fall back to transformed coords
        pass
    return vertices


def _add_gradient_to_patch(
    ax: Any,
    patch: Any,
    base_color: str,
    orientation: str = "vertical",
    alpha: float = 0.85,
    layer: str = "above",
) -> None:
    if plt is None or mcolors is None:
        return
    vertices = _patch_vertices_in_data(patch)
    if vertices is None or len(vertices) == 0:
        return
    xs = vertices[:, 0]
    ys = vertices[:, 1]
    x0, x1 = xs.min(), xs.max()
    y0, y1 = ys.min(), ys.max()
    if x0 == x1 or y0 == y1:
        return

    gradient = np.linspace(0, 1, 256)
    if orientation == "horizontal":
        data = gradient.reshape(1, -1)
        start = _blend_colors(base_color, _TEXT_COLOR, 0.85)
        end = _blend_colors(base_color, _BACKGROUND_COLOR, 0.85)
    else:
        data = gradient.reshape(-1, 1)
        # origin is "lower", so the first row maps to the bottom of the shape;
        # fade bottom into the panel while keeping the top vibrant.
        start = _blend_colors(base_color, _BACKGROUND_COLOR, 0.9)
        end = _blend_colors(base_color, _TEXT_COLOR, 0.6)

    cmap = mcolors.LinearSegmentedColormap.from_list(
        f"{base_color}-{orientation}",
        [start, end],
    )
    zorder = patch.get_zorder() + (0.01 if layer == "above" else -0.01)
    ax.imshow(
        data,
        aspect="auto",
        cmap=cmap,
        extent=[x0, x1, y0, y1],
        origin="lower",
        transform=ax.transData,
        clip_path=patch,
        clip_on=True,
        alpha=alpha,
        zorder=zorder,
    )


def _add_line_shading(
    ax: Any,
    times: list[datetime],
    values: list[float],
    color: str,
) -> None:
    baseline = [0.0] * len(times)
    base_color = _blend_colors(color, _BACKGROUND_COLOR, 0.45)
    fill = ax.fill_between(
        times,
        baseline,
        values,
        color=base_color,
        alpha=0.28,
        linewidth=0,
        label="_nolegend_",
        zorder=1,
    )
    if PathPatch is None:
        return
    for path in fill.get_paths():
        patch = PathPatch(path, facecolor="none", edgecolor="none")
        patch.set_transform(fill.get_transform())
        patch.set_zorder(fill.get_zorder() - 0.01)
        ax.add_patch(patch)
        _add_gradient_to_patch(ax, patch, color, orientation="vertical", layer="below")


def _palette(count: int) -> list[Any]:
    if count <= len(_STACK_COLORS):
        return _STACK_COLORS[:count]
    if mcolors is None:
        repeats = (count + len(_STACK_COLORS) - 1) // len(_STACK_COLORS)
        return (_STACK_COLORS * repeats)[:count]
    palette: list[str] = []
    variant = 0
    while len(palette) < count:
        mix_target = _TEXT_COLOR if variant % 2 == 0 else _BACKGROUND_COLOR
        mix_ratio = min(0.35, 0.12 * variant)
        for base_color in _STACK_COLORS:
            palette.append(_blend_colors(base_color, mix_target, mix_ratio))
            if len(palette) == count:
                break
        variant += 1
    return palette


def _bar_palette(base_color: str, count: int) -> list[Any]:
    if count == 0:
        return []
    if not base_color:
        return _palette(count)
    if mcolors is None:
        return [base_color] * count
    if count == 1:
        return [base_color]
    try:
        base_rgb = mcolors.to_rgb(base_color)
        panel_rgb = mcolors.to_rgb(_PANEL_COLOR)
    except ValueError:
        return _palette(count)
    shades: list[str] = []
    for idx in range(count):
        blend = idx / max(1, count - 1)
        intensity = 0.45 + 0.45 * (1 - blend)
        color_rgb = tuple(
            intensity * base + (1 - intensity) * panel
            for base, panel in zip(base_rgb, panel_rgb)
        )
        shades.append(mcolors.to_hex(color_rgb))
    return shades


if plt is not None:  # pragma: no cover - executed when matplotlib is installed
    _configure_theme()


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
    fig, ax = _theme_figure((12, 5))
    p50 = [entry["p50"] * 1000 for entry in series]
    p95 = [entry["p95"] * 1000 for entry in series]
    p99 = [entry["p99"] * 1000 for entry in series]
    layers = [
        p50,
        [max(0.0, p95[i] - p50[i]) for i in range(len(p50))],
        [max(0.0, p99[i] - p95[i]) for i in range(len(p50))],
    ]
    base_labels = ["P50", "P95", "P99"]
    colors = [_P50_COLOR, _P95_COLOR, _P99_COLOR]
    percentile_values = [p50, p95, p99]
    averages = [sum(values) / len(values) for values in percentile_values]
    legend_labels = [
        f"{label} · avg {avg:.0f} ms"
        for label, avg in zip(base_labels, averages)
    ]
    collections = ax.stackplot(
        times,
        *layers,
        colors=colors,
        labels=legend_labels,
        alpha=0.9,
    )
    _enhance_stackplot(ax, collections, colors)
    ax.set_ylabel("Latency (ms)")
    ax.set_xlabel("Time")
    ax.set_title("HTTP Latency", loc="left", pad=26)
    ax.set_ylim(bottom=0)
    legend = ax.legend(
        frameon=False,
        loc="upper left",
        ncol=1,
        bbox_to_anchor=(1.02, 1.02),
        borderaxespad=0,
    )
    _restyle_legend(legend)

    ax.margins(x=0.01)
    if mdates:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    _apply_background_gradient(ax)
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


def _series_averages(series: list[list[float]]) -> list[float]:
    averages: list[float] = []
    for values in series:
        averages.append(sum(values) / len(values) if values else 0.0)
    return averages


def _plot_stack(
    times: list[datetime],
    labels: list[str],
    series: list[list[float]],
    output: Path,
    title: str,
    ylabel: str,
    *,
    legend_title: str | None = "Endpoints",
    averages: list[float] | None = None,
) -> None:
    _require_matplotlib()
    if not times or not labels:
        return
    fig, ax = _theme_figure((12, 5))
    palette = _palette(len(labels))
    legend_labels = labels
    if averages is not None:
        legend_labels = [
            f"{label} · avg {avg:.2f} rps"
            for label, avg in zip(labels, averages)
        ]
    collections = ax.stackplot(times, *series, labels=legend_labels, colors=palette, alpha=0.9)
    _enhance_stackplot(ax, collections, palette)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Time")
    ax.set_title(title, loc="left", pad=18)
    ax.set_ylim(bottom=0)
    legend = ax.legend(
        loc="upper left",
        bbox_to_anchor=(1.02, 1.02),
        frameon=False,
        title=legend_title or "",
    )
    if legend_title is None:
        legend.set_title(None)
    _restyle_legend(legend)
    ax.margins(x=0.01)
    if mdates:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    _apply_background_gradient(ax)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _plot_line_series(
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
    fig, ax = _theme_figure((12, 5))
    palette = _palette(len(labels))
    for label, values, color in zip(labels, series, palette):
        _add_line_shading(ax, times, values, color)
        ax.plot(times, values, label=label, color=color, linewidth=2.1)
        ax.scatter(
            times,
            values,
            color=color,
            s=14,
            edgecolors=_BACKGROUND_COLOR,
            linewidths=0.4,
            alpha=0.9,
        )
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Time")
    ax.set_title(title, loc="left", pad=22)
    ax.set_ylim(bottom=0)
    legend = ax.legend(
        loc="upper left",
        bbox_to_anchor=(1.02, 1.02),
        frameon=False,
        title="Top endpoints",
    )
    _restyle_legend(legend)
    ax.margins(x=0.01)
    if mdates:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    _apply_background_gradient(ax)
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
    if not stats:
        return
    labels = [item["label"] for item in stats]
    x = range(len(labels))
    fig_width = max(8.0, len(labels) * 1.1)
    fig, ax = _theme_figure((fig_width, 5))
    percentile_tracks = [
        ("P50", [item["p50"] * 1000 for item in stats], _P50_COLOR),
        ("P95", [item["p95"] * 1000 for item in stats], _P95_COLOR),
        ("P99", [item["p99"] * 1000 for item in stats], _P99_COLOR),
    ]
    for label, values, color in percentile_tracks:
        ax.plot(x, values, label=label, color=color, linewidth=2.2)
        ax.scatter(x, values, color=color, s=30, edgecolors=_BACKGROUND_COLOR, linewidths=0.6)

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.set_ylabel("Latency (ms)")
    ax.set_xlabel("Endpoint")
    ax.set_title("HTTP Latency Percentiles", loc="left", pad=18)
    ax.set_ylim(bottom=0)
    legend = ax.legend(frameon=False, ncol=3, loc="upper left", bbox_to_anchor=(0, 1.12))
    _restyle_legend(legend)
    highlighted = max(stats, key=lambda item: item["p99"])
    idx = stats.index(highlighted)
    ax.annotate(
        f"Peak P99: {highlighted['p99'] * 1000:.0f} ms",
        xy=(idx, highlighted["p99"] * 1000),
        xytext=(0, -35),
        textcoords="offset points",
        arrowprops=dict(arrowstyle="->", color=_P99_COLOR, lw=1.2),
        color=_P99_COLOR,
        ha="center",
    )
    _apply_background_gradient(ax)
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
    if not data:
        return
    labels = [label for label, _ in data]
    values = [value for _, value in data]
    height = max(4.0, len(labels) * 0.55 + 2)
    fig, ax = _theme_figure((max(7.0, len(labels) * 0.9), height))
    palette = _bar_palette(color, len(labels))
    positions = list(range(len(labels)))
    bars = ax.barh(positions, values, color=palette, alpha=0.95, edgecolor="none")
    ax.set_yticks(positions)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()  # Top performers first
    ax.set_xlabel(ylabel)
    ax.set_title(title, loc="left", pad=18)
    ax.set_xlim(left=0)
    ax.margins(y=0.02)
    for bar, color in zip(bars, palette):
        bar.set_facecolor(_blend_colors(color, _BACKGROUND_COLOR, 0.35))
        bar.set_alpha(0.65)
        _add_gradient_to_patch(ax, bar, color, orientation="horizontal")
    if hasattr(ax, "bar_label"):
        ax.bar_label(
            bars,
            labels=[f"{value:.2f}" for value in values],
            padding=6,
            color=_TEXT_COLOR,
            fontsize=10,
        )
    _apply_background_gradient(ax)
    fig.tight_layout()
    fig.savefig(output, dpi=150, bbox_inches="tight")
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
                legend_title="Top endpoints",
                averages=_series_averages(throughput_series),
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
                legend_title="Error endpoints",
                averages=_series_averages(error_series),
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
        help=(
            "Path to metrics snapshot JSON or directory containing JSON fragments"
            " (default: metrics_snapshot.json)"
        ),
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
    snapshot = _load_snapshot_source(args.snapshot)
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
