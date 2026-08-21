"""Director Evolution Center API (Phase 12.2, GPT spec).

Endpoints:
- GET  /api/director/evolution/stats             Policy Performance + Win Rate + accumulation
- GET  /api/director/evolution/candidates        Candidate Queue (with stable ids)
- POST /api/director/evolution/candidates/{id}/approve
- POST /api/director/evolution/candidates/{id}/reject
- GET  /api/director/evolution/history           Approval History + Rollback Center log
- POST /api/director/evolution/rollback          Restore the previous policy snapshot
- POST /api/director/evolution/mock-data         Seed the mock source (500 shots / 3 projects / 1000 feedback)

``source`` query param: ``production`` (default, real Director Memory) or
``mock`` (deterministic synthetic dataset for the Dashboard acceptance).
"""

from __future__ import annotations

import random
import shutil
from pathlib import Path
from threading import Lock
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.director.evolution import ControlledEvolution
from backend.director.evolution.policy_candidate import PolicyCandidate
from backend.director.memory import DirectorMemory
from backend.director.policy_router import DEFAULT_POLICY_PATH

router = APIRouter(prefix="/api/director/evolution", tags=["director-evolution"])

PRODUCTION_MEMORY_ROOT = Path("backend/director/memory/storage")
PRODUCTION_VERSIONS_DIR = Path("backend/director/evolution/versions")
MOCK_ROOT = Path("storage/director_evolution_mock")

_evolutions: dict[str, ControlledEvolution] = {}
_overrides: dict[str, ControlledEvolution] = {}
_lock = Lock()

WINNER_LABEL = {"rule-v2": "rule", "llm-qwen": "qwen", "hybrid": "hybrid"}


class _CandidateId:
    @staticmethod
    def encode(candidate: PolicyCandidate) -> str:
        return f"{candidate.scene_type}|{candidate.from_director}->{candidate.to_director}"

    @staticmethod
    def match(candidate: PolicyCandidate, candidate_id: str) -> bool:
        return _CandidateId.encode(candidate) == candidate_id


def set_evolution(source: str, evolution: ControlledEvolution) -> None:
    """Test hook: pin an in-memory evolution instance for a source."""
    with _lock:
        _overrides[source] = evolution


def get_evolution(source: str = "production") -> ControlledEvolution:
    with _lock:
        if source in _overrides:
            return _overrides[source]
        if source not in _evolutions:
            _evolutions[source] = (
                _build_mock_evolution() if source == "mock" else _build_production_evolution()
            )
        return _evolutions[source]


def _build_production_evolution() -> ControlledEvolution:
    memory = DirectorMemory(PRODUCTION_MEMORY_ROOT)
    return ControlledEvolution(
        memory.policy, policy_path=DEFAULT_POLICY_PATH,
        versions_dir=PRODUCTION_VERSIONS_DIR,
        director_memory=memory,
    )


def _build_mock_evolution() -> ControlledEvolution:
    MOCK_ROOT.mkdir(parents=True, exist_ok=True)
    policy_path = MOCK_ROOT / "policy.yaml"
    if not policy_path.exists():
        shutil.copyfile(DEFAULT_POLICY_PATH, policy_path)
    memory = DirectorMemory(MOCK_ROOT / "memory")
    summary = memory.accumulation()
    if summary["shots"] < 500 or summary["projects"] < 3 or summary["feedback_records"] < 1000:
        _seed_mock(memory)
    return ControlledEvolution(
        memory.policy, policy_path=policy_path,
        versions_dir=MOCK_ROOT / "versions",
        director_memory=memory,
    )


def _seed_mock(memory: DirectorMemory) -> None:
    """Deterministic synthetic dataset: 504 shots / 3 projects / 1008 feedback."""
    rng = random.Random(20260806)
    projects = [
        ("mock_sci_fi", "ep01", "科幻", "cold_blue", {"action": 82.0, "dialogue": 88.0}),
        ("mock_ancient", "ep01", "古装", "warm_light", {"action": 90.0, "dialogue": 80.0}),
        ("mock_kids", "ep02", "儿童动画", "pastel", {"world": 86.0, "emotion": 84.0}),
    ]
    scene_types = ["action", "dialogue", "world", "emotion"]
    directors = ["rule-v2", "llm-qwen"]
    issues = ["low_motion", "emotion_too_strong", "static_video", "too_dark"]
    shot_index = 0
    entries = []
    for project_id, episode, genre, style_profile, preferred in projects:
        for scene_type in scene_types:
            base = preferred.get(scene_type, 80.0)
            for director in directors:
                for _ in range(21):  # 3 x 4 x 2 x 21 = 504 shots
                    shot_index += 1
                    avg = base + (3.0 if director == "llm-qwen" else -3.0) + rng.uniform(-1.5, 1.5)
                    entries.append({
                        "shot_id": f"mock_{shot_index:03d}",
                        "director": director,
                        "scene_type": scene_type,
                        "shot_type": "medium",
                        "intent": "dialogue_beat",
                        "camera": {"movement": "static"},
                        "project_id": project_id,
                        "episode": episode,
                        "genre": genre,
                        "style": style_profile,
                        "quality_score": round(max(50.0, min(100.0, avg)), 1),
                        "feedback": {"items": [
                            {"issue": issues[(shot_index + i) % len(issues)], "category": "motion",
                             "severity": "medium", "suggestion": "fix"}
                            for i in range(2)
                        ]},
                        "production_cost": round(rng.uniform(3.0, 25.0), 2),
                        "generation_time": round(rng.uniform(8.0, 90.0), 1),
                        "human_score": round(rng.uniform(60.0, 98.0), 1),
                        "revision_count": rng.randint(0, 3),
                        "final_approved": bool(rng.random() < 0.8),
                    })
    memory.bulk_record(entries)


# ------------------------------------------------------------- request models
class ActionRequest(BaseModel):
    reason: str = Field("", description="Approval / rejection / rollback reason")


# --------------------------------------------------------------- stats
@router.get("/stats")
def stats(source: str = "production"):
    evolution = get_evolution(source)
    if evolution.director_memory is None:
        raise HTTPException(status_code=503, detail="director memory not configured")
    memory = evolution.director_memory
    experiences = memory.shot.experiences()

    rows: dict[tuple, dict] = {}
    for exp in experiences:
        key = (exp.scene_type, exp.director)
        row = rows.setdefault(key, {
            "scene_type": exp.scene_type, "director": exp.director,
            "shots": 0, "sum_score": 0.0, "sum_cost": 0.0, "sum_time": 0.0,
            "sum_human": 0.0, "revisions": 0, "human_count": 0,
        })
        row["shots"] += 1
        if exp.quality_score is not None:
            row["sum_score"] += exp.quality_score
        if exp.production_cost is not None:
            row["sum_cost"] += exp.production_cost
        if exp.generation_time is not None:
            row["sum_time"] += exp.generation_time
        if exp.human_score is not None:
            row["sum_human"] += exp.human_score
            row["human_count"] += 1
        row["revisions"] += max(exp.revision_count or 0, 0)

    policy_performance = []
    win_counts = {"rule": 0, "qwen": 0, "hybrid": 0}
    by_scene: dict[str, list[dict]] = {}
    for row in rows.values():
        entry = {
            "scene_type": row["scene_type"],
            "director": row["director"],
            "shots": row["shots"],
            "avg_score": round(row["sum_score"] / row["shots"], 1) if row["shots"] else None,
            "avg_cost": round(row["sum_cost"] / row["shots"], 2) if row["shots"] else None,
            "avg_generation_time": round(row["sum_time"] / row["shots"], 1) if row["shots"] else None,
            "avg_human_score": round(row["sum_human"] / row["human_count"], 1) if row["human_count"] else None,
            "revisions": row["revisions"],
        }
        policy_performance.append(entry)
        by_scene.setdefault(row["scene_type"], []).append(entry)

    win_rate = []
    for scene_type, rows_for_scene in by_scene.items():
        best = max(rows_for_scene, key=lambda r: r["avg_score"] or 0)
        label = WINNER_LABEL.get(best["director"], "hybrid")
        win_counts[label] += 1
        win_rate.append({"scene_type": scene_type, "winner": best["director"],
                         "avg_score": best["avg_score"], "shots": best["shots"]})

    return {
        "source": source,
        "policy_version": evolution._policy_dict().get("version"),
        "routes": evolution._policy_dict().get("routes", {}),
        "policy_learning": evolution.config,
        "accumulation": memory.accumulation(),
        "policy_performance": policy_performance,
        "win_rate": {"counts": win_counts, "by_scene_type": win_rate},
    }


# ------------------------------------------------------------ candidates
@router.get("/candidates")
def candidates(source: str = "production"):
    evolution = get_evolution(source)
    proposal = evolution.propose()
    items = [
        {**candidate.to_dict(), "id": _CandidateId.encode(candidate)}
        for candidate in proposal["candidates"]
    ]
    return {
        "mode": proposal["mode"],
        "min_samples": evolution.min_samples,
        "confidence_threshold": evolution.confidence_threshold,
        "count": len(items),
        "candidates": items,
    }


def _find_candidate(evolution: ControlledEvolution, candidate_id: str) -> PolicyCandidate:
    for candidate in evolution.analyze():
        if _CandidateId.match(candidate, candidate_id):
            return candidate
    raise HTTPException(status_code=404, detail=f"candidate not found: {candidate_id}")


@router.post("/candidates/{candidate_id}/approve")
def approve_candidate(candidate_id: str, body: Optional[ActionRequest] = None, source: str = "production"):
    evolution = get_evolution(source)
    candidate = _find_candidate(evolution, candidate_id)
    try:
        result = evolution.approve(candidate, approved_by=body.reason if body and body.reason else "human")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return result


@router.post("/candidates/{candidate_id}/reject")
def reject_candidate(candidate_id: str, body: Optional[ActionRequest] = None, source: str = "production"):
    evolution = get_evolution(source)
    candidate = _find_candidate(evolution, candidate_id)
    return evolution.reject(
        candidate, reason=(body.reason if body and body.reason else ""),
        rejected_by="human",
    )


# -------------------------------------------------------------- history
@router.get("/history")
def history(source: str = "production"):
    evolution = get_evolution(source)
    return {"entries": evolution.versions.entries()}


@router.post("/rollback")
def rollback(body: Optional[ActionRequest] = None, source: str = "production"):
    evolution = get_evolution(source)
    try:
        return evolution.rollback(
            reason=(body.reason if body and body.reason else "human_rollback")
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/mock-data")
def seed_mock():
    """(Re)seed the mock dataset; returns the accumulation summary."""
    evolution = _build_mock_evolution()
    return {"source": "mock", "accumulation": evolution.memory.accumulation()}
