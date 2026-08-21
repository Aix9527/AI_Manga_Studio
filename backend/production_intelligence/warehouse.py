"""B1 EventWarehouse + MetricsEngine (Phase 13.5-B, GPT spec).

Raw Event（事实表）→ Metric Aggregation → Analytics 三层结构。
事件 append-only，带 audit_id（审计关联 100%）；聚合层从事件重建
EpisodeMetric / ShotMetric，供 B2 Analytics 消费。
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from backend.production_intelligence.model import (
    EVENT_TYPES,
    EpisodeMetric,
    ProductionEvent,
    ShotMetric,
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class EventWarehouse:
    """事件事实表 + 指标聚合（JSON 持久化）。"""

    def __init__(self, root: str | Path = "storage/production_intelligence"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._events: dict[str, dict] = self._load("events.json")
        self._shots: dict[str, dict] = self._load("shot_metrics.json")
        self._episodes: dict[str, dict] = self._load("episode_metrics.json")

    # ------------------------------------------------------------ io
    def _load(self, name: str) -> dict[str, dict]:
        path = self.root / name
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _save(self, name: str, data: dict[str, dict]) -> None:
        path = self.root / name
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    # ------------------------------------------------------------ events
    def record_event(
        self,
        *,
        event_type: str,
        project_id: str = "",
        episode_id: str = "",
        shot_id: str = "",
        actor: str = "pipeline",
        audit_id: str = "",
        payload: dict | None = None,
        created_at: str = "",
    ) -> dict:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"invalid event type: {event_type} (allowed: {EVENT_TYPES})")
        if not audit_id:
            audit_id = _new_id("AUD")
        event = ProductionEvent(
            id=_new_id("EV"),
            event_type=event_type,
            project_id=project_id,
            episode_id=episode_id,
            shot_id=shot_id,
            actor=actor,
            audit_id=audit_id,
            payload=payload or {},
            created_at=created_at or _now(),
        )
        with self._lock:
            self._events[event.id] = event.to_dict()
            self._save("events.json", self._events)
        # 增量聚合（shot / episode）
        self._aggregate_shot(shot_id) if shot_id else None
        self._aggregate_episode(episode_id) if episode_id else None
        return event.to_dict()

    def list_events(
        self,
        *,
        event_type: str | None = None,
        project_id: str | None = None,
        episode_id: str | None = None,
        shot_id: str | None = None,
    ) -> list[dict]:
        rows = list(self._events.values())
        if event_type:
            rows = [r for r in rows if r.get("event_type") == event_type]
        if project_id:
            rows = [r for r in rows if r.get("project_id") == project_id]
        if episode_id:
            rows = [r for r in rows if r.get("episode_id") == episode_id]
        if shot_id:
            rows = [r for r in rows if r.get("shot_id") == shot_id]
        rows.sort(key=lambda r: r.get("created_at", ""))
        return rows

    # ------------------------------------------------------------ metrics
    def _events_for(self, *, shot_id: str = "", episode_id: str = "") -> list[ProductionEvent]:
        rows = self.list_events(shot_id=shot_id or None, episode_id=episode_id or None)
        return [ProductionEvent.from_dict(raw) for raw in rows]

    def _aggregate_shot(self, shot_id: str) -> ShotMetric:
        events = self._events_for(shot_id=shot_id)
        if not events:
            return ShotMetric(id=_new_id("SM"), shot_id=shot_id)
        metric = ShotMetric(
            id=f"SM_{shot_id}",
            shot_id=shot_id,
            episode_id=events[0].episode_id,
            project_id=events[0].project_id,
        )
        attempts = 0
        revisions = 0
        failed = 0
        quality_sum = 0.0
        quality_n = 0
        for ev in events:
            p = ev.payload or {}
            if ev.event_type == "generation_start":
                attempts += 1
                metric.director = metric.director or p.get("director", "")
                metric.prompt_version = metric.prompt_version or p.get("prompt_version", "")
                metric.shot_dna_id = metric.shot_dna_id or p.get("shot_dna_id", "")
            elif ev.event_type == "generation_end":
                metric.identity_score = max(metric.identity_score, float(p.get("identity_score", 0.0)))
                metric.vision_score = max(metric.vision_score, float(p.get("vision_score", 0.0)))
                metric.motion_score = max(metric.motion_score, float(p.get("motion_score", 0.0)))
                quality_sum += float(p.get("quality", 0.0))
                quality_n += 1
            elif ev.event_type == "qc_failed":
                failed += 1
            elif ev.event_type == "revision_created":
                revisions += 1
            elif ev.event_type == "approval_passed":
                metric.success = True
            elif ev.event_type == "cost_recorded":
                metric.cost += float(p.get("cost", 0.0))
        metric.generation_attempts = max(attempts, 1)
        metric.revision_count = revisions
        metric.quality = round(quality_sum / quality_n, 3) if quality_n else 0.0
        metric.success = failed == 0 and metric.success
        metric.created_at = _now()
        with self._lock:
            self._shots[metric.id] = metric.to_dict()
            self._save("shot_metrics.json", self._shots)
        return metric

    def _aggregate_episode(self, episode_id: str) -> EpisodeMetric:
        events = self._events_for(episode_id=episode_id)
        if not events:
            return EpisodeMetric(id=_new_id("EM"), episode_id=episode_id)
        metric = EpisodeMetric(
            id=f"EM_{episode_id}",
            episode_id=episode_id,
            project_id=events[0].project_id,
        )
        shots = {ev.shot_id for ev in events if ev.shot_id}
        shot_metrics = [self.shot_metric(sid) for sid in shots if self.shot_metric(sid)]
        if shot_metrics:
            metric.avg_qc = round(sum(s.quality for s in shot_metrics) / len(shot_metrics), 3)
            metric.failure_rate = round(sum(0 if s.success else 1 for s in shot_metrics) / len(shot_metrics), 3)
            metric.cost_actual = round(sum(s.cost for s in shot_metrics), 2)
            metric.director_mix = ",".join(sorted({s.director for s in shot_metrics if s.director}))
            versions = [s.prompt_version for s in shot_metrics if s.prompt_version]
            metric.prompt_version = versions[0] if versions else ""
        for ev in events:
            p = ev.payload or {}
            if ev.event_type == "cost_recorded" and "planned_cost" in p:
                metric.cost_planned += float(p["planned_cost"])
            if ev.event_type == "generation_end":
                metric.retention = max(metric.retention, float(p.get("retention", 0.0)))
                metric.hook_score = max(metric.hook_score, float(p.get("hook_score", 0.0)))
                metric.cliffhanger = max(metric.cliffhanger, float(p.get("cliffhanger", 0.0)))
                metric.lead_time_s = max(metric.lead_time_s, float(p.get("lead_time_s", 0.0)))
        metric.created_at = _now()
        with self._lock:
            self._episodes[metric.id] = metric.to_dict()
            self._save("episode_metrics.json", self._episodes)
        return metric

    # ------------------------------------------------------------ readers
    def shot_metric(self, shot_id: str) -> ShotMetric | None:
        with self._lock:
            raw = self._shots.get(f"SM_{shot_id}")
        return ShotMetric.from_dict(raw) if raw else None

    def episode_metric(self, episode_id: str) -> EpisodeMetric | None:
        with self._lock:
            raw = self._episodes.get(f"EM_{episode_id}")
        return EpisodeMetric.from_dict(raw) if raw else None

    def shot_metrics(self, project_id: str | None = None) -> list[ShotMetric]:
        with self._lock:
            rows = [ShotMetric.from_dict(raw) for raw in self._shots.values()]
        if project_id:
            rows = [r for r in rows if r.project_id == project_id]
        return rows

    def episode_metrics(self, project_id: str | None = None) -> list[EpisodeMetric]:
        with self._lock:
            rows = [EpisodeMetric.from_dict(raw) for raw in self._episodes.values()]
        if project_id:
            rows = [r for r in rows if r.project_id == project_id]
        return rows

    # ------------------------------------------------------------ stats
    def stats(self) -> dict:
        with self._lock:
            by_type: dict[str, int] = {}
            for raw in self._events.values():
                by_type[raw.get("event_type", "")] = by_type.get(raw.get("event_type", ""), 0) + 1
            audited = sum(1 for raw in self._events.values() if raw.get("audit_id"))
        return {
            "events": len(self._events),
            "events_by_type": by_type,
            "audit_coverage": round(audited / len(self._events), 3) if self._events else 1.0,
            "shot_metrics": len(self._shots),
            "episode_metrics": len(self._episodes),
        }