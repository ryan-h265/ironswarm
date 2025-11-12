from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from threading import Lock
from time import time
from typing import Any

DEFAULT_LATENCY_BUCKETS: tuple[float, ...] = (
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)

LabelsType = Mapping[str, str] | None
_LabelKey = tuple[tuple[str, str], ...]


def _normalize_labels(labels: LabelsType) -> _LabelKey:
    if not labels:
        return tuple()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _labels_from_key(key: _LabelKey) -> dict[str, str]:
    return dict(key)


@dataclass
class _HistogramState:
    bucket_counts: list[int]
    sum: float = 0.0
    count: int = 0

    @classmethod
    def create(cls, bucket_count: int) -> _HistogramState:
        # +1 bucket for +Inf
        return cls(bucket_counts=[0] * (bucket_count + 1))

    def observe(self, value: float, bucket_index: int):
        self.bucket_counts[bucket_index] += 1
        self.sum += value
        self.count += 1

    def export(self) -> dict[str, Any]:
        return {
            "bucket_counts": list(self.bucket_counts),
            "sum": self.sum,
            "count": self.count,
        }


class CounterMetric:
    """Thread-safe counter family supporting arbitrary label sets."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._values: dict[_LabelKey, float] = {}
        self._lock = Lock()

    def inc(self, amount: float = 1.0, labels: LabelsType = None) -> None:
        if amount < 0:
            raise ValueError("Counters can only be incremented by non-negative values.")
        key = _normalize_labels(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def snapshot(self, reset: bool = False) -> dict[str, Any]:
        with self._lock:
            samples = [
                {"labels": _labels_from_key(label_key), "value": value}
                for label_key, value in self._values.items()
            ]
            if reset:
                self._values = {}
        return {
            "name": self.name,
            "description": self.description,
            "samples": samples,
            "type": "counter",
        }


class HistogramMetric:
    """Thread-safe histogram family mirroring Prometheus bucket semantics."""

    def __init__(
        self,
        name: str,
        description: str = "",
        buckets: Sequence[float] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.buckets: tuple[float, ...] = tuple(sorted(buckets or DEFAULT_LATENCY_BUCKETS))
        self._states: dict[_LabelKey, _HistogramState] = {}
        self._lock = Lock()

    def _bucket_index(self, value: float) -> int:
        for idx, boundary in enumerate(self.buckets):
            if value <= boundary:
                return idx
        return len(self.buckets)  # +Inf bucket

    def observe(self, value: float, labels: LabelsType = None) -> None:
        key = _normalize_labels(labels)
        bucket_index = self._bucket_index(value)
        with self._lock:
            state = self._states.get(key)
            if state is None:
                state = _HistogramState.create(len(self.buckets))
                self._states[key] = state
            state.observe(value, bucket_index)

    def snapshot(self, reset: bool = False) -> dict[str, Any]:
        with self._lock:
            samples = []
            for label_key, state in self._states.items():
                cumulative = 0
                bucket_exports = []
                for boundary, bucket_count in zip(self.buckets, state.bucket_counts[:-1], strict=False):
                    cumulative += bucket_count
                    bucket_exports.append({"le": boundary, "count": cumulative})

                cumulative += state.bucket_counts[-1]
                bucket_exports.append({"le": "+Inf", "count": cumulative})

                samples.append(
                    {
                        "labels": _labels_from_key(label_key),
                        "sum": state.sum,
                        "count": state.count,
                        "buckets": bucket_exports,
                    }
                )

            if reset:
                self._states = {}

        return {
            "name": self.name,
            "description": self.description,
            "buckets": list(self.buckets),
            "samples": samples,
            "type": "histogram",
        }


class MetricCollector:
    """Central registry for counters and histograms used across the process."""

    def __init__(self) -> None:
        self._counters: dict[str, CounterMetric] = {}
        self._histograms: dict[str, HistogramMetric] = {}
        self._lock = Lock()
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._events_lock = Lock()

    def register_counter(self, name: str, description: str = "") -> CounterMetric:
        with self._lock:
            metric = self._counters.get(name)
            if metric is None:
                metric = CounterMetric(name, description=description)
                self._counters[name] = metric
            return metric

    def register_histogram(
        self,
        name: str,
        description: str = "",
        buckets: Sequence[float] | None = None,
    ) -> HistogramMetric:
        with self._lock:
            metric = self._histograms.get(name)
            if metric is None:
                metric = HistogramMetric(name, description=description, buckets=buckets)
                self._histograms[name] = metric
            return metric

    def inc(
        self,
        name: str,
        amount: float = 1.0,
        labels: LabelsType = None,
        description: str = "",
    ) -> None:
        counter = self.register_counter(name, description)
        counter.inc(amount=amount, labels=labels)

    def observe(
        self,
        name: str,
        value: float,
        labels: LabelsType = None,
        description: str = "",
        buckets: Sequence[float] | None = None,
    ) -> None:
        histogram = self.register_histogram(name, description=description, buckets=buckets)
        histogram.observe(value=value, labels=labels)

    def record_event(self, name: str, payload: Mapping[str, Any]) -> None:
        with self._events_lock:
            events = self._events.setdefault(name, [])
            events.append(dict(payload))

    def snapshot(self, reset: bool = False) -> dict[str, Any]:
        counters = {name: metric.snapshot(reset=reset) for name, metric in self._counters.items()}
        histograms = {
            name: metric.snapshot(reset=reset) for name, metric in self._histograms.items()
        }
        with self._events_lock:
            events = {name: list(entries) for name, entries in self._events.items()}
            if reset:
                self._events = {}
        return {
            "timestamp": time(),
            "counters": counters,
            "histograms": histograms,
            "events": events,
        }

    def reset(self) -> None:
        self.snapshot(reset=True)


collector = MetricCollector()


def get_collector() -> MetricCollector:
    return collector
