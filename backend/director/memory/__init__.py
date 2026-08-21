"""Director Memory (Phase 11.1).

Records every director decision (rule / LLM / policy route), the quality
feedback that later arrives (Identity Gate, Quality Gate, Vision Critic,
human review), failures, and aggregates them into success patterns and
per-policy statistics so Phase 11.3 can evolve the router policy with real
evidence (stats window + rollback + human approval).
"""

from __future__ import annotations

import json
import threading
import uuid

from backend.director.memory.scope import MemoryScope, scope_from_experience
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


@dataclass
class DirectorExperience:
    """One recorded director decision + its quality outcome."""

    shot_id: str
    scene_type: str = ""
    shot_type: str = ""
    director: str = ""            # rule-v2 | llm-qwen | llm-openai | llm-claude | mixture
    intent: str = ""
    camera: dict = field(default_factory=dict)
    lighting: dict = field(default_factory=dict)
    emotion_curve: list[dict] = field(default_factory=list)
    quality_score: float | None = None
    feedback: dict = field(default_factory=dict)
    # Phase 12.1 Production Data Accumulation (GPT spec):
    project_id: str = ""
    episode: str = ""
    genre: str = ""                        # Phase 12.3 isolation dimension
    style: str = ""                        # visual style profile
    character_universe: str = ""
    production_cost: float | None = None   # cost meter seconds (or cost units)
    generation_time: float | None = None   # wall-clock seconds
    human_score: float | None = None       # 0-100 human review
    revision_count: int = 0
    final_approved: bool | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)


class _JsonStore:
    """Small thread-safe JSON store keyed by id."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self._data: dict = _load_json(path)

    def _save(self) -> None:
        with self._lock:
            _save_json(self.path, self._data)

    def get(self, key: str) -> dict | None:
        with self._lock:
            return self._data.get(key)

    def put(self, key: str, value: dict) -> None:
        with self._lock:
            self._data[key] = value
            self._save()

    def all(self) -> dict:
        with self._lock:
            return dict(self._data)

    def put_many(self, items: dict[str, dict]) -> None:
        """Bulk insert (single save) — used by mock seeding / imports."""
        with self._lock:
            self._data.update(items)
            self._save()


class ShotMemory(_JsonStore):
    """Per-shot director decisions (the foundation record)."""

    def __init__(self, root: str | Path):
        super().__init__(Path(root) / "shot_memory.json")

    def record(self, exp: DirectorExperience) -> None:
        """Store the decision; keep previously recorded quality feedback when a
        shot is re-planned (retry / re-run) and the new decision carries none."""
        existing = self.get(exp.shot_id) or {}
        data = exp.to_dict()
        if existing:
            if data.get("quality_score") is None and existing.get("quality_score") is not None:
                data["quality_score"] = existing["quality_score"]
            if not data.get("feedback") and existing.get("feedback"):
                data["feedback"] = existing["feedback"]
        self.put(exp.shot_id, data)

    def record_quality(
        self,
        shot_id: str,
        quality_score: float,
        feedback: dict | None = None,
        *,
        production_cost: float | None = None,
        generation_time: float | None = None,
        human_score: float | None = None,
        revision_count: int | None = None,
        final_approved: bool | None = None,
    ) -> None:
        raw = self.get(shot_id)
        if not raw:
            return
        raw["quality_score"] = float(quality_score)
        if feedback:
            raw["feedback"] = dict(raw.get("feedback", {}), **feedback)
        for key, value in {
            "production_cost": production_cost,
            "generation_time": generation_time,
            "human_score": human_score,
            "revision_count": revision_count,
            "final_approved": final_approved,
        }.items():
            if value is not None:
                raw[key] = value
        raw["updated_at"] = _now()
        self.put(shot_id, raw)

    def experiences(self) -> list[DirectorExperience]:
        return [DirectorExperience(**raw) for raw in self.all().values()]


class FailureMemory(_JsonStore):
    """Director failures (validator reject, identity fail, quality fail)."""

    def __init__(self, root: str | Path):
        super().__init__(Path(root) / "failure_memory.json")

    def record(self, shot_id: str, director: str, failure_type: str, detail: str = "") -> None:
        key = f"{shot_id}:{uuid.uuid4().hex[:8]}"
        self.put(key, {
            "shot_id": shot_id, "director": director, "failure_type": failure_type,
            "detail": detail, "created_at": _now(),
        })

    def count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for raw in self.all().values():
            counts[str(raw.get("failure_type", "unknown"))] = counts.get(str(raw.get("failure_type", "unknown")), 0) + 1
        return counts


class SuccessPattern(_JsonStore):
    """Aggregates high-quality (shot_type, director, camera) patterns."""

    def __init__(self, root: str | Path):
        super().__init__(Path(root) / "success_pattern.json")

    def patterns(
        self,
        experiences: list[DirectorExperience] | None = None,
        min_samples: int = 3,
    ) -> list[dict]:
        """Aggregate high-quality patterns scoped by
        (project_scope|genre|style, shot_type, director, camera movement).

        ``experiences`` defaults to this store's own records so persisted
        patterns can be re-read; pass ``shot.experiences()`` for live data.
        """
        buckets: dict[tuple, dict] = {}
        for exp in experiences if experiences is not None else _experiences_from(self):
            if exp.quality_score is None:
                continue
            scope = scope_from_experience(exp)
            key = (scope.scope_key(), exp.shot_type, exp.director, exp.camera.get("movement", ""))
            bucket = buckets.setdefault(key, {"n": 0, "total": 0.0, "sample": exp})
            bucket["n"] += 1
            bucket["total"] += exp.quality_score
        patterns = []
        for (scope_key, shot_type, director, movement), bucket in buckets.items():
            if bucket["n"] < min_samples:
                continue
            patterns.append({
                "scope_key": scope_key, "shot_type": shot_type,
                "director": director, "movement": movement,
                "samples": bucket["n"],
                "avg_quality": round(bucket["total"] / bucket["n"], 1),
            })
        return sorted(patterns, key=lambda p: -p["avg_quality"])


class PolicyMemory(_JsonStore):
    """Per (scene_type, director) quality stats feeding Phase 11.3 evolution."""

    def __init__(self, root: str | Path):
        super().__init__(Path(root) / "policy_memory.json")

    def record(self, exp: DirectorExperience) -> None:
        """Record one shot's quality under its (scene_type, director) key.

        Idempotent per shot: ``record_decision`` followed by
        ``record_quality`` updates the same row instead of double counting.
        """
        with self._lock:
            self._apply(exp)
            self._save()

    def record_many(self, experiences: list[DirectorExperience]) -> None:
        """Bulk version of :meth:`record` (single save) for seeding/imports."""
        with self._lock:
            for exp in experiences:
                self._apply(exp)
            self._save()

    def _apply(self, exp: DirectorExperience) -> None:
        scope = scope_from_experience(exp)
        key = f"{scope.scope_key()}|{exp.scene_type}|{exp.director}"
        raw = self._data.get(key) or {
            "scene_type": exp.scene_type, "director": exp.director,
            "project_scope": scope.project_scope, "genre": exp.genre,
            "style": exp.style, "scope_key": scope.scope_key(),
            "by_shot": {}, "sum_quality": 0.0,
        }
        by_shot = raw.setdefault("by_shot", {})
        previous = by_shot.get(exp.shot_id)
        if isinstance(previous, (int, float)) and previous != exp.quality_score:
            raw["sum_quality"] = raw.get("sum_quality", 0.0) - float(previous)
        by_shot[exp.shot_id] = exp.quality_score
        if isinstance(exp.quality_score, (int, float)):
            raw["sum_quality"] = raw.get("sum_quality", 0.0) + float(exp.quality_score)
        self._data[key] = raw

    def stats(self) -> list[dict]:
        rows = []
        for raw in self.all().values():
            by_shot = raw.get("by_shot") or {}
            quals = [q for q in by_shot.values() if isinstance(q, (int, float))]
            rows.append({
                "scene_type": raw.get("scene_type", ""),
                "director": raw.get("director", ""),
                "project_scope": raw.get("project_scope", ""),
                "genre": raw.get("genre", ""),
                "style": raw.get("style", ""),
                "scope_key": raw.get("scope_key", ""),
                "shots": len(by_shot),
                "avg_quality": round(sum(quals) / len(quals), 1) if quals else None,
            })
        return sorted(rows, key=lambda r: (r["scene_type"], - (r["avg_quality"] or 0)))

    def suggest(self, scene_type: str, director_a: str = "rule-v2", director_b: str = "llm-qwen",
                min_samples: int = 5, scope_key: str = "") -> dict:
        """Recommend the better director for a (scope, scene type) from real samples.

        Phase 12.3: when ``scope_key`` is given, only rows from that memory
        scope are compared so cross-project experience never pollutes the vote.
        """
        rows = {
            r["director"]: r
            for r in self.stats()
            if r["scene_type"] == scene_type and (not scope_key or r.get("scope_key") == scope_key)
        }
        a, b = rows.get(director_a), rows.get(director_b)
        if not a or not b or a["shots"] < min_samples or b["shots"] < min_samples:
            return {"scene_type": scene_type, "winner": None, "reason": "insufficient_samples"}
        winner = director_a if (a["avg_quality"] or 0) >= (b["avg_quality"] or 0) else director_b
        return {
            "scene_type": scene_type, "winner": winner,
            director_a: a, director_b: b,
            "reason": "avg_quality comparison",
        }


# Phase 11.2: issue -> deterministic next-shot adjustment applied by the
# director (never by the critic). Keyed by stable ISSUE_MAP keywords.
FEEDBACK_ADJUSTMENTS: dict[str, dict] = {
    "emotion_too_strong": {"emotion_scale": 0.55, "note": "emotion_too_strong:reduce_expression_level"},
    "emotion_too_weak": {"emotion_scale": 1.4, "note": "emotion_too_weak:increase_expression_level"},
    "static_video": {"avoid_movements": ["static"], "replacement_movement": "slow push-in",
                     "note": "static_video:add_motion"},
    "low_motion": {"avoid_movements": ["static", "pan"], "replacement_movement": "slow push-in",
                   "note": "low_motion:bump_motion"},
    "low_motion_flow": {"avoid_movements": ["static", "pan"], "replacement_movement": "slow push-in",
                        "note": "low_motion_flow:bump_motion"},
    "flicker_motion_curve": {"avoid_movements": ["handheld", "orbit", "crane", "tracking"],
                             "replacement_movement": "static", "note": "flicker:stabilize"},
    "motion_blur": {"avoid_movements": ["handheld", "tracking", "orbit"],
                    "replacement_movement": "static", "note": "motion_blur:reduce_motion"},
    "camera_physics": {"avoid_movements": ["orbit", "crane"], "replacement_movement": "static",
                       "note": "camera_physics:fix_combination"},
    "too_dark": {"lighting_fix": "soft_glow", "note": "too_dark:brighten"},
    "too_bright": {"lighting_fix": "low_key", "note": "too_bright:reduce_exposure"},
    "mosaic": {"note": "mosaic:reduce_denoise"},
    "block_artifact": {"note": "block_artifact:super_resolution"},
    "flickering": {"avoid_movements": ["handheld", "orbit", "crane"], "replacement_movement": "static",
                   "note": "flickering:stabilize"},
    "character_drift": {"note": "character_drift:lock_reference"},
    "character_missing": {"note": "character_missing:reinsert_character"},
    "composition_imbalance": {"note": "composition:rebalance_framing"},
    "missing_continuity": {"note": "continuity:thread_previous"},
}


class DirectorMemory:
    """Facade over the four memory stores (GPT Phase 11.1 spec)."""

    def __init__(self, root: str | Path = "backend/director/memory/storage"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.shot = ShotMemory(self.root)
        self.failure = FailureMemory(self.root)
        self.pattern = SuccessPattern(self.root)
        self.policy = PolicyMemory(self.root)

    def record_decision(
        self,
        shot_id: str,
        director: str,
        *,
        scene_type: str = "",
        shot_type: str = "",
        intent: str = "",
        camera: dict | None = None,
        lighting: dict | None = None,
        emotion_curve: list[dict] | None = None,
        project_id: str = "",
        episode: str = "",
        genre: str = "",
        style: str = "",
        character_universe: str = "",
    ) -> DirectorExperience:
        exp = DirectorExperience(
            shot_id=shot_id, scene_type=scene_type, shot_type=shot_type,
            director=director, intent=intent, camera=camera or {},
            lighting=lighting or {}, emotion_curve=emotion_curve or [],
            project_id=project_id, episode=episode,
            genre=genre, style=style, character_universe=character_universe,
        )
        self.shot.record(exp)
        self.policy.record(exp)
        return exp

    def record_quality(
        self,
        shot_id: str,
        quality_score: float,
        feedback: dict | None = None,
        *,
        production_cost: float | None = None,
        generation_time: float | None = None,
        human_score: float | None = None,
        revision_count: int | None = None,
        final_approved: bool | None = None,
    ) -> None:
        self.shot.record_quality(
            shot_id, quality_score, feedback,
            production_cost=production_cost,
            generation_time=generation_time,
            human_score=human_score,
            revision_count=revision_count,
            final_approved=final_approved,
        )
        raw = self.shot.get(shot_id)
        if raw:
            self.policy.record(DirectorExperience(**raw))

    def record_failure(self, shot_id: str, director: str, failure_type: str, detail: str = "") -> None:
        self.failure.record(shot_id, director, failure_type, detail)

    def adjustments_for(self, shot_id: str) -> dict:
        """Phase 11.2: merge the stored feedback of one shot into the next-shot
        adjustment table the director applies (emotion scale, camera movement
        avoidance, lighting fix, traceable note)."""
        raw = self.shot.get(shot_id)
        if not raw:
            return {}
        items = (raw.get("feedback") or {}).get("items") or []
        merged: dict = {}
        for item in items:
            rule = FEEDBACK_ADJUSTMENTS.get(str(item.get("issue") or ""))
            if not rule:
                continue
            for key, value in rule.items():
                if key == "avoid_movements":
                    avoid = merged.setdefault("avoid_movements", [])
                    for movement in value:
                        if movement not in avoid:
                            avoid.append(movement)
                else:
                    merged[key] = value
        return merged

    def accumulation(self) -> dict:
        """Phase 12.1 targets: >=500 shots, >=3 projects, >=1000 feedback records."""
        shots = self.shot.experiences()
        projects = {exp.project_id for exp in shots if exp.project_id}
        feedback_records = sum(
            len((exp.feedback or {}).get("items") or []) for exp in shots
        )
        revisions = sum(max(exp.revision_count, 0) for exp in shots)
        return {
            "shots": len(shots),
            "projects": len(projects),
            "episodes": len({(exp.project_id, exp.episode) for exp in shots if exp.project_id and exp.episode}),
            "feedback_records": feedback_records,
            "revisions": revisions,
            "targets": {
                "shots": 500, "projects": 3, "feedback_records": 1000,
            },
        }

    def bulk_record(self, entries: list[dict]) -> None:
        """Bulk import of decision + quality records (single saves).

        Each entry maps to one DirectorExperience with optional production
        fields; used by the Phase 12.2 mock dataset and production imports.
        """
        if not entries:
            return
        shot_items: dict[str, dict] = {}
        experiences: list[DirectorExperience] = []
        for entry in entries:
            exp = DirectorExperience(
                shot_id=str(entry.get("shot_id") or ""),
                scene_type=str(entry.get("scene_type") or ""),
                shot_type=str(entry.get("shot_type") or ""),
                director=str(entry.get("director") or ""),
                intent=str(entry.get("intent") or ""),
                camera=dict(entry.get("camera") or {}),
                lighting=dict(entry.get("lighting") or {}),
                emotion_curve=list(entry.get("emotion_curve") or []),
                quality_score=entry.get("quality_score"),
                feedback=dict(entry.get("feedback") or {}),
                project_id=str(entry.get("project_id") or ""),
                episode=str(entry.get("episode") or ""),
                genre=str(entry.get("genre") or ""),
                style=str(entry.get("style") or ""),
                character_universe=str(entry.get("character_universe") or ""),
                production_cost=entry.get("production_cost"),
                generation_time=entry.get("generation_time"),
                human_score=entry.get("human_score"),
                revision_count=int(entry.get("revision_count") or 0),
                final_approved=entry.get("final_approved"),
            )
            shot_items[exp.shot_id] = exp.to_dict()
            experiences.append(exp)
        self.shot.put_many(shot_items)
        self.policy.record_many(experiences)

    def stats_by_scope(self) -> dict:
        """Phase 12.3: policy stats grouped by memory scope for cross-project
        comparison without mixing genres."""
        scoped: dict[str, list[dict]] = {}
        for row in self.policy.stats():
            scoped.setdefault(row.get("scope_key") or "", []).append(row)
        return {
            "scopes": len(scoped),
            "by_scope": {
                scope_key: {
                    "rows": rows,
                    "winner": max(rows, key=lambda r: r.get("avg_quality") or 0)
                    if rows and any(r.get("avg_quality") is not None for r in rows) else None,
                }
                for scope_key, rows in scoped.items()
            },
        }

    def stats(self) -> dict:
        return {
            "shots": len(self.shot.all()),
            "failures": self.failure.count_by_type(),
            "policy": self.policy.stats(),
            "patterns": self.pattern.patterns(self.shot.experiences()),
        }


def _experiences_from(store: _JsonStore) -> list[DirectorExperience]:
    return [DirectorExperience(**raw) for raw in store.all().values() if raw.get("shot_id")]
