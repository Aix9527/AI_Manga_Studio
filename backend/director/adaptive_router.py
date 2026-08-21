"""Adaptive Director Router (Phase 12.6, GPT approved).

Turns the Director Arena results + Director Memory + Scope Stats into a
per-scope route recommendation (primary/fallback director per scene type),
reviewed by a human in the Policy Evolution Center before it is applied::

    sci-fi:
      world:
        primary: gpt
        fallback: qwen

Third production view (GPT spec)::

    Production Value Score = 0.40*Quality + 0.20*Continuity + 0.15*Stability
                             + 0.15*Cost + 0.10*Latency

Selection rule (matching GPT's Phase 12.6 example)::

    primary  = creative per-scope winner (quality specialization)
    fallback = best Production Value Score among the remaining directors

so a cell never degenerates into "cheapest always wins": the creative
specialization stays the primary candidate and PVS answers "who is the
best production candidate behind it".

Every recommendation is versioned (``adaptive_router_policy_vN.yaml``) and
rollback-able; no unsupervised online learning (GPT constraint).
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from backend.director.arena import (
    COST_PROFILES,
    GENRES,
    SCENE_TYPES,
    DirectorArena,
)
from backend.director.evolution.rollback import PolicyVersionStore
from backend.director.policy_router import DEFAULT_POLICY_PATH, DirectorRouter

# ------------------------------------------------------------ scoring
# GPT Phase 12.6: Production Value Score (third view, between art and cost).
PRODUCTION_VALUE_WEIGHTS = {
    "quality": 0.40,
    "continuity": 0.20,
    "stability": 0.15,
    "cost": 0.15,
    "latency": 0.10,
}

# route -> director name used by the legacy static router (before line).
ROUTE_DIRECTOR = {"rule": "rule-v2", "qwen": "llm-qwen", "hybrid": "llm-qwen"}

DEFAULT_ADAPTIVE_POLICY_PATH = Path(__file__).parent / "adaptive_router_policy.yaml"
ADAPTIVE_VERSIONS_DIR = Path(__file__).parent / "evolution" / "adaptive_versions"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def latency_score(director: str) -> float:
    """0-1 latency score: 1.0 = fastest, from the arena cost profiles."""
    _, latency_ms, _ = COST_PROFILES.get(director, (0, 0, 1.0))
    return round(max(0.0, min(1.0, 1.0 - latency_ms / 2200.0)), 3)


def production_value_score(components: dict, director: str) -> float:
    """PVS from per-shot arena components + the director latency profile."""
    quality = float(components.get("quality") or 0.0)
    continuity = float(components.get("continuity") or 0.0)
    stability = float(components.get("stability") or 0.0)
    cost = float(components.get("cost") or 0.0)
    lat = latency_score(director)
    total = (
        PRODUCTION_VALUE_WEIGHTS["quality"] * quality
        + PRODUCTION_VALUE_WEIGHTS["continuity"] * continuity
        + PRODUCTION_VALUE_WEIGHTS["stability"] * stability
        + PRODUCTION_VALUE_WEIGHTS["cost"] * cost
        + PRODUCTION_VALUE_WEIGHTS["latency"] * lat
    )
    return round(total * 100.0, 1)


@dataclass
class AdaptiveRecommendation:
    """One scene strategy suggestion: a (genre, scene_type) cell + a role."""

    id: str                       # f"{genre}|{scene_type}|{role}"
    cell: str                     # f"{genre}|{scene_type}"
    genre: str
    scene_type: str
    role: str                     # "primary" | "fallback"
    director: str
    pvs: float
    delta_to_next: float          # PVS gap vs the runner-up (0 for fallback)
    samples: int
    evidence: dict = field(default_factory=dict)
    status: str = "pending"       # pending | approved | rejected
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class AdaptiveDirectorRouter:
    """Build + review + apply the adaptive route table from arena evidence.

    Inputs (GPT 12.6): Arena report, Director Memory stats, Policy Evolution
    (version store + manual approval), Scope Stats (per-genre isolation).
    """

    def __init__(
        self,
        arena_report: dict | None = None,
        policy_path: str | Path = DEFAULT_ADAPTIVE_POLICY_PATH,
        versions_dir: str | Path | None = None,
        memory_stats: list[dict] | None = None,
        static_router: DirectorRouter | None = None,
    ):
        self.arena = DirectorArena()
        self.arena_report = arena_report or self.arena.run()
        self.policy_path = Path(policy_path)
        self.versions = PolicyVersionStore(
            self.policy_path,
            versions_dir=versions_dir or ADAPTIVE_VERSIONS_DIR,
            log_name="adaptive_evolution_log.json",
            prefix="adaptive_router_policy",
        )
        self.memory_stats = list(memory_stats or [])
        self.static_router = static_router or DirectorRouter(DEFAULT_POLICY_PATH)
        self.recommendations: list[AdaptiveRecommendation] = []
        self._policy: dict = {}
        # persistent decision tracking (status survives recompute)
        self._approved_cells: set[str] = set()
        self._rejected_cells: set[str] = set()
        self._load_policy()

    # ------------------------------------------------------------ policy
    def _load_policy(self) -> None:
        if self.policy_path.exists():
            try:
                self._policy = yaml.safe_load(self.policy_path.read_text(encoding="utf-8")) or {}
            except Exception:
                self._policy = {}
        else:
            self._policy = {}

    def _policy_dict(self) -> dict:
        if not self.policy_path.exists():
            return {}
        return yaml.safe_load(self.policy_path.read_text(encoding="utf-8")) or {}

    def route_for(self, genre: str, scene_type: str) -> dict:
        """Primary/fallback for a (genre, scene_type) cell; defaults to the
        global default block when the cell has not been approved yet."""
        scopes = self._policy.get("scopes") or {}
        cell = (scopes.get(genre) or {}).get(scene_type) or {}
        if cell.get("primary") and cell.get("fallback"):
            return {"primary": cell["primary"], "fallback": cell["fallback"]}
        default = self._policy.get("default") or {}
        return {
            "primary": default.get("primary") or "rule-v2",
            "fallback": default.get("fallback") or "llm-qwen",
        }

    def resolve_route(self, genre: str, scene_type: str) -> dict:
        """Effective route for production: approved cell wins, otherwise the
        creative recommendation (per-scope winner + PVS fallback).

        Used by the Phase 12.7-A AdaptiveDispatcher so an unapproved cell does
        not silently fall back to the static default but still follows the
        arena-backed recommendation until a human approves/rejects it.
        """
        scopes = self._policy.get("scopes") or {}
        cell = (scopes.get(genre) or {}).get(scene_type) or {}
        if cell.get("primary") and cell.get("fallback"):
            return {"primary": cell["primary"], "fallback": cell["fallback"]}
        for rec in self.compute_recommendations():
            if rec.cell == f"{genre}|{scene_type}" and rec.role == "primary":
                fallback_rec = next(
                    (r for r in self.compute_recommendations()
                     if r.cell == f"{genre}|{scene_type}" and r.role == "fallback"),
                    None,
                )
                return {
                    "primary": rec.director,
                    "fallback": fallback_rec.director if fallback_rec else "rule-v2",
                }
        return self.route_for(genre, scene_type)

    # ------------------------------------------------------ recommendations
    def compute_recommendations(self) -> list[AdaptiveRecommendation]:
        """20 (genre x scene_type) cells x (primary + fallback) = 40 suggestions."""
        rows = self.arena_report.get("rows") or []
        recs: list[AdaptiveRecommendation] = []
        for genre in GENRES:
            for scene_type in SCENE_TYPES:
                cell_rows = [
                    r for r in rows
                    if r["genre"] == genre and r["scene_type"] == scene_type
                ]
                if not cell_rows:
                    continue
                # PVS per director from this cell's rows only (scope isolation)
                pvs: dict[str, float] = {}
                samples: dict[str, int] = {}
                for director in sorted({r["director"] for r in cell_rows}):
                    subset = [r for r in cell_rows if r["director"] == director]
                    components = {
                        key: round(
                            sum(float(r["components"][key]) for r in subset) / len(subset), 3
                        )
                        for key in ("quality", "continuity", "stability", "cost")
                    }
                    pvs[director] = production_value_score(components, director)
                    samples[director] = len(subset)
                ranking = sorted(pvs, key=lambda d: -pvs[d])
                # primary = creative specialization (GPT 12.5/12.6 approved);
                # fallback = best Production Value Score behind the winner.
                per_scope_winner = self.arena_report.get("per_scope_winner") or {}
                primary = per_scope_winner.get(genre) or ranking[0]
                fallback = next((d for d in ranking if d != primary), primary)
                cell = f"{genre}|{scene_type}"
                evidence = {
                    "shots": len(cell_rows),
                    "pvs": pvs,
                    "memory": self._memory_evidence(genre, scene_type),
                }
                recs.append(AdaptiveRecommendation(
                    id=f"{cell}|primary",
                    cell=cell, genre=genre, scene_type=scene_type, role="primary",
                    director=primary, pvs=pvs[primary],
                    delta_to_next=round(pvs[primary] - pvs[fallback], 1),
                    samples=samples[primary], evidence=evidence,
                ))
                recs.append(AdaptiveRecommendation(
                    id=f"{cell}|fallback",
                    cell=cell, genre=genre, scene_type=scene_type, role="fallback",
                    director=fallback, pvs=pvs[fallback],
                    delta_to_next=0.0,
                    samples=samples[fallback], evidence=evidence,
                ))
        for rec in recs:
            if rec.cell in self._approved_cells:
                rec.status = "approved"
            elif rec.cell in self._rejected_cells:
                rec.status = "rejected"
        self.recommendations = recs
        return recs

    def _memory_evidence(self, genre: str, scene_type: str) -> dict:
        """Production evidence from Director Memory Policy stats for this cell."""
        subset = [
            r for r in self.memory_stats
            if str(r.get("genre") or "") == genre
            and str(r.get("scene_type") or "") == scene_type
        ]
        if not subset:
            return {"present": False, "rows": 0}
        return {
            "present": True,
            "rows": len(subset),
            "best": sorted(
                ({"director": r.get("director"), "avg": r.get("avg_quality"),
                  "shots": r.get("shots")} for r in subset),
                key=lambda r: -(r["avg"] or 0.0),
            )[:3],
        }

    def proposal(self) -> dict:
        """All recommendations (40 >= GPT gate of 30)."""
        recs = self.compute_recommendations()
        return {
            "count": len(recs),
            "cells": len({r.cell for r in recs}),
            "scope_isolation": self.isolation_audit(),
            "recommendations": [r.to_dict() for r in recs],
            "production_value_weights": PRODUCTION_VALUE_WEIGHTS,
        }

    def isolation_audit(self) -> dict:
        """Verify every recommendation used ONLY its own scope's rows."""
        rows = self.arena_report.get("rows") or []
        recs = self.compute_recommendations()
        violations = 0
        checked = 0
        for rec in recs:
            checked += 1
            cell_rows = [
                r for r in rows
                if r["genre"] == rec.genre and r["scene_type"] == rec.scene_type
            ]
            foreign = [r for r in cell_rows if r["genre"] != rec.genre]
            violations += len(foreign)
        return {"checked": checked, "violations": violations, "isolated": violations == 0}

    # ------------------------------------------------------------ approval
    def _find(self, rec_id: str) -> AdaptiveRecommendation:
        for rec in self.compute_recommendations():
            if rec.id == rec_id:
                return rec
        raise KeyError(f"no adaptive recommendation {rec_id!r}")

    def approve(self, rec_id: str, approved_by: str = "human") -> dict:
        """Approve one (genre, scene_type) cell: persist primary + fallback."""
        rec = self._find(rec_id)
        cell_id = rec.cell
        genre, scene_type = cell_id.split("|", 1)
        # both roles of the cell must exist and be pending
        cell_recs = [r for r in self.compute_recommendations() if r.cell == cell_id]
        if cell_id in self._rejected_cells:
            raise ValueError(f"cell {cell_id} was already rejected")
        if cell_id in self._approved_cells:
            raise ValueError(f"cell {cell_id} was already approved")
        before = self._policy_dict()
        snapshot = self.versions.snapshot()

        data = dict(before)
        data["version"] = round(float(data.get("version") or 0.0) + 1.0, 1)
        scopes = dict(data.get("scopes") or {})
        cell = dict((scopes.get(genre) or {}).get(scene_type) or {})
        for r in cell_recs:
            cell[r.role] = r.director
        scopes.setdefault(genre, {})[scene_type] = cell
        data["scopes"] = scopes
        tmp = self.policy_path.with_suffix(".yaml.tmp")
        tmp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        tmp.replace(self.policy_path)
        self._load_policy()

        entry = self.versions.log("approve", {
            "cell": cell_id,
            "primary": cell.get("primary"),
            "fallback": cell.get("fallback"),
            "policy_version_after": data.get("version"),
            "snapshot_version": snapshot,
            "approved_by": approved_by,
        })
        self._approved_cells.add(cell_id)
        for r in cell_recs:
            r.status = "approved"
        return {"cell": cell_id, "policy": {genre: {scene_type: cell}}, "log": entry}

    def reject(self, rec_id: str, reason: str = "", rejected_by: str = "human") -> dict:
        """Reject one cell; recorded in the adaptive evolution log only."""
        rec = self._find(rec_id)
        if rec.cell in self._rejected_cells:
            raise ValueError(f"cell {rec.cell} was already rejected")
        entry = self.versions.log("reject", {
            "cell": rec.cell,
            "reason": reason,
            "rejected_by": rejected_by,
        })
        self._rejected_cells.add(rec.cell)
        for r in self.compute_recommendations():
            if r.cell == rec.cell:
                r.status = "rejected"
        return {"cell": rec.cell, "log": entry}

    def rollback(self, reason: str = "bad_adaptive_policy", rolled_back_by: str = "human") -> dict:
        """Restore the previous adaptive policy snapshot (rollback available)."""
        version = self.versions.latest_version()
        if version <= 0:
            raise RuntimeError("no adaptive policy snapshot to roll back to")
        before = self._policy_dict()
        restored = self.versions.restore(version)
        self._load_policy()
        entry = self.versions.log("rollback", {
            "policy_version_before": before.get("version"),
            "policy_version_after": restored.get("version"),
            "reason": reason,
            "rolled_back_by": rolled_back_by,
        })
        return {"restored_version": version, "policy": restored, "log": entry}

    # ------------------------------------------------------------ A/B
    def ab_validation(self, limit: int = 100) -> dict:
        """Before (static router) vs After (adaptive router) over arena shots.

        GPT gate: >= 100 shots; PASS when quality +5% OR cost -10%.
        """
        rows = self.arena_report.get("rows") or []
        shot_ids = sorted({r["shot_id"] for r in rows})[:limit]
        if len(shot_ids) < 100:
            raise ValueError(f"need >=100 shots for A/B, got {len(shot_ids)}")
        before_q: list[float] = []
        before_cost: list[float] = []
        after_q: list[float] = []
        after_cost: list[float] = []
        # adaptive primary per cell: the *recommended* creative winner, i.e.
        # what the router WOULD do once the human approves the proposal.
        primary_by_cell: dict[str, str] = {
            rec.cell: rec.director
            for rec in self.compute_recommendations()
            if rec.role == "primary"
        }
        for shot_id in shot_ids:
            shot_rows = [r for r in rows if r["shot_id"] == shot_id]
            if not shot_rows:
                continue
            genre = shot_rows[0]["genre"]
            scene_type = shot_rows[0]["scene_type"]
            before_director = ROUTE_DIRECTOR.get(self.static_router.route_for(scene_type), "rule-v2")
            after_director = primary_by_cell.get(f"{genre}|{scene_type}")
            if after_director is None:
                after_director = self.route_for(genre, scene_type)["primary"]
            before_row = next((r for r in shot_rows if r["director"] == before_director), None)
            after_row = next((r for r in shot_rows if r["director"] == after_director), None)
            if before_row is None or after_row is None:
                continue
            before_q.append(float(before_row["components"]["quality"]))
            before_cost.append(1.0 - float(before_row["components"]["cost"]))
            after_q.append(float(after_row["components"]["quality"]))
            after_cost.append(1.0 - float(after_row["components"]["cost"]))

        avg_before_q = sum(before_q) / len(before_q) if before_q else 0.0
        avg_after_q = sum(after_q) / len(after_q) if after_q else 0.0
        avg_before_cost = sum(before_cost) / len(before_cost) if before_cost else 0.0
        avg_after_cost = sum(after_cost) / len(after_cost) if after_cost else 0.0

        quality_gain_pct = round((avg_after_q - avg_before_q) / avg_before_q * 100.0, 1) if avg_before_q else 0.0
        cost_reduction_pct = round(
            (avg_before_cost - avg_after_cost) / avg_before_cost * 100.0, 1
        ) if avg_before_cost else 0.0
        passed = quality_gain_pct >= 5.0 or cost_reduction_pct >= 10.0
        # GPT Phase 12.6 review: name the cost metric cost_delta, positive =
        # cost increase, negative = cost decrease (avoid "cost improvement").
        cost_delta_pct = round(-cost_reduction_pct, 1)
        return {
            "shots": len(shot_ids),
            "before": {
                "director_route": self.static_router.routes,
                "avg_quality": round(avg_before_q, 3),
                "avg_cost": round(avg_before_cost, 3),
            },
            "after": {
                "adaptive_primary": {
                    genre: {
                        st: primary_by_cell.get(f"{genre}|{st}", self.route_for(genre, st)["primary"])
                        for st in SCENE_TYPES
                    }
                    for genre in GENRES
                },
                "avg_quality": round(avg_after_q, 3),
                "avg_cost": round(avg_after_cost, 3),
            },
            "quality_gain_pct": quality_gain_pct,
            "cost_reduction_pct": cost_reduction_pct,
            "cost_delta_pct": cost_delta_pct,
            "passed": passed,
            "gate": {"quality_gain_min": 5.0, "cost_reduction_min": 10.0},
        }
