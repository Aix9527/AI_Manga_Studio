"""
Metrics — Prometheus-compatible metrics (Part 19)

Exposes application metrics for monitoring and alerting.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Counter:
    """Monotonically increasing counter."""
    name: str
    help: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    _value: int = 0

    def inc(self, amount: int = 1) -> None:
        self._value += amount

    @property
    def value(self) -> int:
        return self._value


@dataclass
class Gauge:
    """A value that can go up and down."""
    name: str
    help: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    _value: float = 0.0

    def set(self, value: float) -> None:
        self._value = value

    def inc(self, amount: float = 1.0) -> None:
        self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        self._value -= amount

    @property
    def value(self) -> float:
        return self._value


@dataclass
class Histogram:
    """Records observations into configurable buckets."""
    name: str
    help: str = ""
    buckets: list[float] = field(default_factory=lambda: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
    labels: dict[str, str] = field(default_factory=dict)
    _count: int = 0
    _sum: float = 0.0
    _buckets: dict[float, int] = field(default_factory=dict)

    def observe(self, value: float) -> None:
        self._count += 1
        self._sum += value
        for bound in self.buckets:
            if value <= bound:
                self._buckets[bound] = self._buckets.get(bound, 0) + 1

    @property
    def count(self) -> int:
        return self._count


class MetricsRegistry:
    """Central metrics collection."""

    def __init__(self) -> None:
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}

    def counter(self, name: str, help: str = "", **labels: str) -> Counter:
        key = f"{name}:{sorted(labels.items())}"
        if key not in self._counters:
            self._counters[key] = Counter(name=name, help=help, labels=dict(labels))
        return self._counters[key]

    def gauge(self, name: str, help: str = "", **labels: str) -> Gauge:
        key = f"{name}:{sorted(labels.items())}"
        if key not in self._gauges:
            self._gauges[key] = Gauge(name=name, help=help, labels=dict(labels))
        return self._gauges[key]

    def histogram(self, name: str, help: str = "",
                  buckets: list[float] | None = None, **labels: str) -> Histogram:
        key = f"{name}:{sorted(labels.items())}"
        if key not in self._histograms:
            self._histograms[key] = Histogram(
                name=name, help=help,
                buckets=buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
                labels=dict(labels),
            )
        return self._histograms[key]

    def export_prometheus(self) -> str:
        """Export all metrics in Prometheus text format."""
        lines: list[str] = []

        for c in self._counters.values():
            label_str = ",".join(f'{k}="{v}"' for k, v in c.labels.items())
            name = f'{c.name}{{{label_str}}}' if label_str else c.name
            lines.append(f"# HELP {c.name} {c.help}")
            lines.append(f"# TYPE {c.name} counter")
            lines.append(f"{name} {c.value}")

        for g in self._gauges.values():
            label_str = ",".join(f'{k}="{v}"' for k, v in g.labels.items())
            name = f'{g.name}{{{label_str}}}' if label_str else g.name
            lines.append(f"# HELP {g.name} {g.help}")
            lines.append(f"# TYPE {g.name} gauge")
            lines.append(f"{name} {g.value}")

        for h in self._histograms.values():
            label_str = ",".join(f'{k}="{v}"' for k, v in h.labels.items())
            name = f'{h.name}{{{label_str}}}' if label_str else h.name
            lines.append(f"# HELP {h.name} {h.help}")
            lines.append(f"# TYPE {h.name} histogram")
            lines.append(f"{name}_count{h._count}")
            lines.append(f"{name}_sum{h._sum}")

        return "\n".join(lines) + "\n"


# Global metrics registry
metrics = MetricsRegistry()

# Predefined metrics
jobs_total = metrics.counter("jobs_total", "Total number of jobs submitted")
jobs_completed = metrics.counter("jobs_completed", "Total completed jobs")
jobs_failed = metrics.counter("jobs_failed", "Total failed jobs")
active_jobs = metrics.gauge("active_jobs", "Currently running jobs")
image_gen_duration = metrics.histogram("image_gen_duration_seconds", "Image generation time")
video_gen_duration = metrics.histogram("video_gen_duration_seconds", "Video generation time")
