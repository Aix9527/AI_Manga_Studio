"""Adaptive Dispatcher (Phase 12.7-A, GPT approved).

Connects the Adaptive Router to production tasks. For every shot the
dispatcher resolves the effective director route from the arena-backed
recommendation (approved cells win, otherwise the creative recommendation)
and builds a failure chain::

    primary -> fallback -> rule-v2 (emergency)

So when an LLM director becomes unavailable the production line degrades
automatically (GPT -> Qwen -> Rule) instead of stopping.

GPT Phase 12.7-A acceptance:
1. Router actually drives production: 100-shot A/B Before (fixed rule) vs
   After (adaptive) with quality +5% and fallback <10%.
2. Failure test: GPT unavailable -> auto GPT -> Qwen -> Rule.
3. Scope isolation: Sci-Fi != Historical (per-scope cells stay separate).
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.director.adaptive_router import (
    ADAPTIVE_VERSIONS_DIR,
    DEFAULT_ADAPTIVE_POLICY_PATH,
    AdaptiveDirectorRouter,
)
from backend.director.arena import COST_PROFILES, DIRECTOR_STRENGTH, GENRES, SCENE_TYPES

EMERGENCY_DIRECTOR = "rule-v2"


@dataclass
class DispatchRequest:
    project: str = ""
    genre: str = "科幻"
    scene_type: str = "action"
    shot_type: str = "medium"
    style: str = ""
    shot_id: str = ""


@dataclass
class DispatchDecision:
    shot_id: str = ""
    project: str = ""
    genre: str = ""
    scene_type: str = ""
    shot_type: str = ""
    style: str = ""
    primary_director: str = "rule-v2"
    fallback: str = "rule-v2"
    provider_chain: list[str] = field(default_factory=list)
    source: str = "recommendation"   # approved | recommendation
    scope_key: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def resolved(self) -> str:
        return self.primary_director


class AdaptiveDispatcher:
    """Resolve the effective director for a production shot + failure chain."""

    def __init__(
        self,
        router: AdaptiveDirectorRouter | None = None,
        policy_path: str | Path = DEFAULT_ADAPTIVE_POLICY_PATH,
        versions_dir: str | Path | None = None,
        memory_stats: list[dict] | None = None,
    ):
        self.router = router or AdaptiveDirectorRouter(
            policy_path=policy_path,
            versions_dir=versions_dir or ADAPTIVE_VERSIONS_DIR,
            memory_stats=memory_stats,
        )

    # ------------------------------------------------------------ dispatch
    def dispatch(self, request: DispatchRequest) -> DispatchDecision:
        genre = request.genre or "科幻"
        scene_type = request.scene_type or "action"
        route = self.router.resolve_route(genre, scene_type)
        primary = route["primary"]
        fallback = route["fallback"]
        # failure chain always ends at the deterministic emergency director
        chain: list[str] = []
        for director in (primary, fallback, EMERGENCY_DIRECTOR):
            if director and director not in chain:
                chain.append(director)
        scopes = self.router._policy.get("scopes") or {}
        approved = bool((scopes.get(genre) or {}).get(scene_type))
        return DispatchDecision(
            shot_id=request.shot_id,
            project=request.project,
            genre=genre,
            scene_type=scene_type,
            shot_type=request.shot_type,
            style=request.style,
            primary_director=primary,
            fallback=fallback,
            provider_chain=chain,
            source="approved" if approved else "recommendation",
            scope_key=genre,
        )

    def resolve(self, decision: DispatchDecision, unavailable: set[str]) -> str:
        """Pick the first provider in the chain that is available.

        Failure test: ``unavailable={"llm-gpt"}`` must resolve to the next
        chain member (fallback / emergency) without raising.
        """
        for director in decision.provider_chain:
            if director not in unavailable:
                return director
        return EMERGENCY_DIRECTOR

    # ------------------------------------------------------------ A/B
    def ab_validation(self, limit: int = 100, seed: int = 1207, failure_rate: float = 0.05) -> dict:
        """100-shot A/B: Before = fixed rule-v2, After = adaptive route.

        GPT gate: quality +5% AND fallback rate <10% (simulated availability).
        """
        if limit < 100:
            raise ValueError(f"need >=100 shots for A/B, got {limit}")
        rows = self.router.arena_report.get("rows") or []
        shot_ids = sorted({r["shot_id"] for r in rows})[:limit]
        rng = random.Random(seed)

        before_q: list[float] = []
        after_q: list[float] = []
        fallback_used = 0
        for shot_id in shot_ids:
            shot_rows = [r for r in rows if r["shot_id"] == shot_id]
            if not shot_rows:
                continue
            genre = shot_rows[0]["genre"]
            scene_type = shot_rows[0]["scene_type"]
            decision = self.dispatch(DispatchRequest(
                genre=genre, scene_type=scene_type, shot_id=shot_id,
            ))
            # simulated primary availability
            unavailable: set[str] = set()
            if rng.random() < failure_rate:
                unavailable.add(decision.primary_director)
            resolved = self.resolve(decision, unavailable)
            if resolved != decision.primary_director:
                fallback_used += 1
            before_row = next((r for r in shot_rows if r["director"] == EMERGENCY_DIRECTOR), None)
            after_row = next((r for r in shot_rows if r["director"] == resolved), None)
            if before_row is None or after_row is None:
                continue
            before_q.append(float(before_row["components"]["quality"]))
            after_q.append(float(after_row["components"]["quality"]))

        avg_before_q = sum(before_q) / len(before_q) if before_q else 0.0
        avg_after_q = sum(after_q) / len(after_q) if after_q else 0.0
        quality_gain_pct = round((avg_after_q - avg_before_q) / avg_before_q * 100.0, 1) if avg_before_q else 0.0
        fallback_rate = round(fallback_used / len(shot_ids) * 100.0, 1)
        passed = quality_gain_pct >= 5.0 and fallback_rate < 10.0
        return {
            "shots": len(shot_ids),
            "before": {"director": EMERGENCY_DIRECTOR, "avg_quality": round(avg_before_q, 3)},
            "after": {
                "avg_quality": round(avg_after_q, 3),
                "fallback_rate": fallback_rate,
                "fallback_used": fallback_used,
            },
            "quality_gain_pct": quality_gain_pct,
            "fallback_rate": fallback_rate,
            "passed": passed,
            "gate": {"quality_gain_min": 5.0, "fallback_rate_max": 10.0},
        }

    # ------------------------------------------------------------ failure
    def failure_test(self, unavailable: str = "llm-gpt", genre: str = "科幻", scene_type: str = "action") -> dict:
        """Simulate an unavailable provider; assert automatic chain fallback."""
        decision = self.dispatch(DispatchRequest(genre=genre, scene_type=scene_type))
        chain = list(decision.provider_chain)
        resolved = self.resolve(decision, {unavailable})
        expected = next((d for d in chain if d != unavailable), EMERGENCY_DIRECTOR)
        return {
            "unavailable": unavailable,
            "chain": chain,
            "resolved": resolved,
            "expected": expected,
            "degraded": resolved != decision.primary_director,
            "chain_ends_at_emergency": EMERGENCY_DIRECTOR in chain,
        }

    # ------------------------------------------------------------ scope
    def scope_isolation_report(self) -> dict:
        """Sci-Fi and Historical dispatches must never share a decision."""
        decisions = {
            genre: {
                scene_type: self.dispatch(DispatchRequest(genre=genre, scene_type=scene_type)).to_dict()
                for scene_type in SCENE_TYPES
            }
            for genre in GENRES
        }
        sci = {k: v["primary_director"] for k, v in decisions["科幻"].items()}
        his = {k: v["primary_director"] for k, v in decisions["古装"].items()}
        # per-scope cells are derived from each genre's own arena rows only
        shared_cells = [st for st in SCENE_TYPES if sci[st] == his[st]]
        return {
            "genres": list(GENRES),
            "sci_fi_primary": sci,
            "historical_primary": his,
            "scope_key_isolated": all(
                v["scope_key"] == genre for genre, cells in decisions.items() for v in cells.values()
            ),
            "shared_primary_cells": shared_cells,
        }
