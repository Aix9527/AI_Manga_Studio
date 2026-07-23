"""
Health — Health check endpoints (Part 19)

Provides health check infrastructure: liveness probe, readiness probe,
component-level health checks.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

HealthCheckFn = Callable[[], Coroutine[Any, Any, bool]]


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health status of a single component."""
    name: str
    status: HealthStatus = HealthStatus.HEALTHY
    message: str = ""
    last_checked: float = field(default_factory=time.time)
    response_time_ms: float = 0.0


class HealthChecker:
    """Aggregates health checks from multiple components."""

    def __init__(self) -> None:
        self._checks: dict[str, tuple[HealthCheckFn, float]] = {}  # name -> (fn, timeout)

    def register(self, name: str, check_fn: HealthCheckFn, timeout: float = 5.0) -> None:
        self._checks[name] = (check_fn, timeout)

    async def check_all(self) -> dict[str, Any]:
        """Run all health checks concurrently and return aggregated status."""
        results: dict[str, ComponentHealth] = {}

        async def _run_check(name: str, fn: HealthCheckFn, timeout: float) -> ComponentHealth:
            comp = ComponentHealth(name=name)
            start = time.monotonic()
            try:
                healthy = await asyncio.wait_for(fn(), timeout=timeout)
                comp.status = HealthStatus.HEALTHY if healthy else HealthStatus.UNHEALTHY
            except asyncio.TimeoutError:
                comp.status = HealthStatus.DEGRADED
                comp.message = "Health check timed out"
            except Exception as e:
                comp.status = HealthStatus.UNHEALTHY
                comp.message = str(e)
            comp.response_time_ms = (time.monotonic() - start) * 1000
            comp.last_checked = time.time()
            return comp

        tasks = [
            _run_check(name, fn, timeout)
            for name, (fn, timeout) in self._checks.items()
        ]

        components = await asyncio.gather(*tasks, return_exceptions=True)

        overall = HealthStatus.HEALTHY
        comps_dict: dict[str, dict[str, Any]] = {}

        for comp in components:
            if isinstance(comp, Exception):
                continue
            comps_dict[comp.name] = {
                "status": comp.status.value,
                "message": comp.message,
                "response_time_ms": round(comp.response_time_ms, 3),
            }
            if comp.status == HealthStatus.UNHEALTHY:
                overall = HealthStatus.UNHEALTHY
            elif comp.status == HealthStatus.DEGRADED and overall != HealthStatus.UNHEALTHY:
                overall = HealthStatus.DEGRADED

        return {
            "status": overall.value,
            "timestamp": time.time(),
            "components": comps_dict,
        }

    async def liveness(self) -> dict[str, str]:
        """Simple liveness check — just returns ok."""
        return {"status": "alive"}


# Global health checker
health_checker = HealthChecker()
