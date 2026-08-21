"""Generation Cost Meter (GPT Stage-A prerequisite).

Records per-shot generation cost (gpu_time, vram_peak, retry) so the studio
can estimate full-film cost automatically.  Costs are appended to the shot
state inside the ChainCheckpoint manifest.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ShotCost:
    shot_id: str = ""
    gpu_time_s: float = 0.0
    vram_peak_gb: float = 0.0
    retry_count: int = 0
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict:
        return {
            "shot": self.shot_id,
            "gpu_time_s": round(self.gpu_time_s, 1),
            "vram_peak_gb": round(self.vram_peak_gb, 2),
            "retry_count": self.retry_count,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class CostMeter:
    """Tracks elapsed generation time per shot and aggregates project cost."""

    def __init__(self):
        self._starts: dict[str, float] = {}
        self._costs: dict[str, ShotCost] = {}

    def start(self, shot_id: str) -> None:
        import datetime as _dt

        self._starts[shot_id] = time.perf_counter()
        cost = self._costs.setdefault(shot_id, ShotCost(shot_id=shot_id))
        cost.started_at = _dt.datetime.now().isoformat(timespec="seconds")

    def stop(
        self,
        shot_id: str,
        *,
        vram_peak_gb: float = 0.0,
        retry_count: int = 0,
    ) -> ShotCost:
        import datetime as _dt

        cost = self._costs.setdefault(shot_id, ShotCost(shot_id=shot_id))
        if shot_id in self._starts:
            cost.gpu_time_s = max(0.0, time.perf_counter() - self._starts.pop(shot_id))
        cost.vram_peak_gb = vram_peak_gb
        cost.retry_count = retry_count
        cost.finished_at = _dt.datetime.now().isoformat(timespec="seconds")
        return cost

    def record(self, shot_id: str, **kwargs: Any) -> ShotCost:
        cost = self._costs.setdefault(shot_id, ShotCost(shot_id=shot_id))
        for key, value in kwargs.items():
            if hasattr(cost, key):
                setattr(cost, key, value)
        return cost

    def summary(self) -> dict:
        total = sum(c.gpu_time_s for c in self._costs.values())
        return {
            "shots": len(self._costs),
            "total_gpu_time_s": round(total, 1),
            "avg_gpu_time_s": round(total / len(self._costs), 1) if self._costs else 0.0,
            "max_vram_peak_gb": round(max((c.vram_peak_gb for c in self._costs.values()), default=0.0), 2),
            "details": [c.to_dict() for c in self._costs.values()],
        }
