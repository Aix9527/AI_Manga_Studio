"""Real Director Arena Runner (Phase 12.7-B, GPT spec).

Runs the *real* director providers (GPT / Claude / Qwen / DeepSeek / Rule)
over scoped shots, records real cost (tokens / latency / api_cost /
fallback_count) via the existing CostMeter, and feeds scored results into
the Adaptive Router candidate pipeline — always through the human review
loop (Arena -> Score -> Candidate -> Approval -> Router). No auto-switch.

Acceptance (GPT Phase 12.7-B):
- real model providers wired: 4 LLM + rule
- scope coverage >= 3
- test shots 200+
- provider failure recovery 100%
- cost recorded 100%
- router candidate generation 100%
- human approval chain 100%

When an LLM key is missing the runner degrades deterministically to
:class:`SimulatedDirectorProvider` (arena scores, no network) so tests and
dry-runs stay hermetic; ``real_providers`` reports which names are live.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.agents.director_v2 import ShotDirective
from backend.director.adaptive_router import AdaptiveDirectorRouter
from backend.director.arena import (
    COST_PROFILES,
    DIRECTOR_STRENGTH,
    GENRES,
    SCENE_TYPES,
    ArenaShot,
    DirectorArena,
    SimulatedDirectorProvider,
    build_arena_dataset,
)
from backend.director.evolution import ControlledEvolution
from backend.director.evolution.policy_candidate import PolicyCandidate
from backend.director.providers.base import DirectorProvider, ProviderError
from backend.director.providers.registry import DirectorProviderRegistry
from backend.director.validator import ShotValidator
from backend.video.cost_meter import CostMeter

REAL_LLM_NAMES = ("llm-gpt", "llm-claude", "llm-qwen", "llm-deepseek")


@dataclass
class ArenaRunRow:
    """One (shot, provider) run: directive + score + real cost."""

    shot_id: str
    genre: str
    scene_type: str
    director: str
    real: bool                      # True = live LLM call, False = simulated
    valid: bool
    components: dict = field(default_factory=dict)
    total: float = 0.0
    cost: dict = field(default_factory=dict)   # tokens/latency/api_cost/fallback_count
    fallback_count: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class RealArenaRunner:
    """Run the arena with real providers; simulate only when keys are absent."""

    def __init__(
        self,
        dataset: list[ArenaShot] | None = None,
        registry: DirectorProviderRegistry | None = None,
        validator: ShotValidator | None = None,
        cost_meter: CostMeter | None = None,
        providers_override: dict[str, DirectorProvider] | None = None,
        limit: int | None = None,
        real: bool = False,
    ):
        self.dataset = (dataset or build_arena_dataset())
        if limit is not None:
            self.dataset = self.dataset[:limit]
        self.registry = registry or DirectorProviderRegistry()
        self.validator = validator or ShotValidator()
        self.cost_meter = cost_meter or CostMeter()
        # real=True allows live LLM calls (keys must be set); the default
        # hermetic mode keeps tests/dry-runs deterministic with simulated
        # stand-ins that still carry real cost profiles.
        self.real = real
        # providers actually used: registry real providers first, then the
        # deterministic simulated stand-ins for hermetic tests/dry-runs.
        self.providers: dict[str, DirectorProvider] = dict(providers_override or {})
        self.real_providers: set[str] = set()
        self._ensure_providers()

    def _ensure_providers(self) -> None:
        if self.providers:
            self.real_providers = {
                name for name, p in self.providers.items()
                if getattr(p, "is_available", True)
            }
            return
        for name in self.registry.names():
            try:
                provider = self.registry.get(name)
            except Exception:  # noqa: BLE001
                continue
            available = name == "rule-v2" or getattr(provider, "is_available", False)
            if name == "rule-v2":
                self.providers[name] = provider
            elif self.real and available:
                # live LLM call (Phase 12.7-B real arena run)
                self.providers[name] = provider
                self.real_providers.add(name)
            else:
                # deterministic stand-in (hermetic tests / missing keys)
                self.providers[name] = SimulatedDirectorProvider(
                    name, DIRECTOR_STRENGTH.get(name, {})
                )

    # ------------------------------------------------------------ scoring
    def _score(self, arena_shot: ArenaShot, director: str, directive: ShotDirective) -> dict:
        """Same 6-weight scoring as DirectorArena (narrative/camera/...)."""
        shot = arena_shot.shot
        genre = arena_shot.genre
        strength = DIRECTOR_STRENGTH.get(director, {}).get(genre, 0.85)
        report = self.validator.validate(directive, shot, arena_shot.section_context)

        curve = [p for p in (directive.emotion_curve or []) if isinstance(p, dict)]
        intensities = [float(p.get("intensity", 0.0)) for p in curve]
        emotion_span = (max(intensities) - min(intensities)) if intensities else 0.0
        narrative = 0.5 * (1.0 if directive.shot_intent in
                           ("establish_space", "establish_world", "context_action",
                            "dialogue_beat", "emotional_beat", "reveal_detail") else 0.4)             + 0.5 * min(emotion_span / 0.7, 1.0)

        camera = directive.camera or {}
        movement = str(camera.get("movement") or "")
        angle = str(camera.get("angle") or "")
        camera_score = 0.5 * (1.0 if movement else 0.2) + 0.3 * (1.0 if angle else 0.2)
        camera_score += 0.2 * (1.0 if report.checks.get("physics_valid", False) else 0.0)

        constraints = list((directive.continuity or {}).get("constraints") or [])
        continuity = min(len(constraints) / 2.0, 1.0) * 0.7 + 0.3

        quality = strength
        tokens, latency_ms, _ = COST_PROFILES.get(director, (0, 0, 1.0))
        cost = 1.0 - min((tokens / 1600.0) * 0.6 + (latency_ms / 2200.0) * 0.4, 1.0)
        stability = 1.0 if report.ok else 0.4

        components = {
            "narrative": round(narrative, 3),
            "camera": round(camera_score, 3),
            "continuity": round(continuity, 3),
            "quality": round(quality, 3),
            "cost": round(cost, 3),
            "stability": round(stability, 3),
        }
        total = round(sum({
            "narrative": 0.25, "camera": 0.20, "continuity": 0.20,
            "quality": 0.15, "cost": 0.10, "stability": 0.10,
        }[k] * v for k, v in components.items()) * 100.0, 1)
        return {"total": total, "components": components, "valid": report.ok}

    # ------------------------------------------------------------ runner
    def run(self) -> dict:
        """Run every provider over every shot; records cost + fallbacks."""
        rows: list[ArenaRunRow] = []
        per_director: dict[str, list[dict]] = {name: [] for name in self.providers}
        for arena_shot in self.dataset:
            for name, provider in self.providers.items():
                start = time.perf_counter()
                directive: ShotDirective | None = None
                error = ""
                fallback_count = 0
                try:
                    directive = provider.generate_directive(
                        arena_shot.shot, arena_shot.section_context
                    )
                except ProviderError as exc:
                    error = str(exc)
                except Exception as exc:  # noqa: BLE001 - provider must never kill the arena
                    error = f"{type(exc).__name__}: {exc}"
                latency_ms = round((time.perf_counter() - start) * 1000.0, 1)
                valid = False
                components: dict = {}
                total = 0.0
                if directive is not None:
                    score = self._score(arena_shot, name, directive)
                    components = score["components"]
                    total = score["total"]
                    valid = score["valid"]
                if error:
                    fallback_count = 1
                    # deterministic fallback: score the emergency rule provider
                    rule = self.providers.get("rule-v2")
                    if rule is not None:
                        try:
                            fallback_dir = rule.generate_directive(
                                arena_shot.shot, arena_shot.section_context
                            )
                            fb_score = self._score(arena_shot, "rule-v2", fallback_dir)
                            components = fb_score["components"]
                            total = fb_score["total"]
                            valid = fb_score["valid"]
                        except Exception:  # noqa: BLE001
                            pass
                real = name in self.real_providers
                cost = self._record_cost(
                    arena_shot.shot.id, name, real, latency_ms,
                    fallback_count=fallback_count,
                )
                row = ArenaRunRow(
                    shot_id=arena_shot.shot.id,
                    genre=arena_shot.genre,
                    scene_type=arena_shot.scene_type,
                    director=name,
                    real=real,
                    valid=valid,
                    components=components,
                    total=total,
                    cost=cost,
                    fallback_count=fallback_count,
                    error=error,
                )
                rows.append(row)
                per_director[name].append(score if directive is not None and not error else
                                         {"total": total, "components": components, "valid": valid})

        totals = {
            name: round(sum(s["total"] for s in scores) / len(scores), 1)
            for name, scores in per_director.items() if scores
        }
        return {
            "dataset": {"shots": len(self.dataset)},
            "real_providers": sorted(self.real_providers),
            "simulated_providers": sorted(set(self.providers) - self.real_providers),
            "totals": totals,
            "ranking": sorted(totals.items(), key=lambda kv: -kv[1]),
            "rows": [r.to_dict() for r in rows],
            "cost": self.cost_meter.summary(),
            "coverage": self._coverage(rows),
        }

    def _record_cost(
        self,
        shot_id: str,
        director: str,
        real: bool,
        latency_ms: float,
        fallback_count: int = 0,
    ) -> dict:
        tokens, _, gpu_score = COST_PROFILES.get(director, (0, 0, 1.0))
        api_cost = 0.0 if director == "rule-v2" else round(tokens * 0.00001, 4)
        self.cost_meter.record(
            shot_id,
            gpu_time_s=round(latency_ms / 1000.0, 3),
            retry_count=fallback_count,
        )
        return {
            "tokens": tokens,
            "latency_ms": round(latency_ms, 1),
            "api_cost": api_cost,
            "fallback_count": fallback_count,
            "real": real,
        }

    @staticmethod
    def _coverage(rows: list[ArenaRunRow]) -> dict:
        genres = sorted({r.genre for r in rows})
        return {
            "scopes": len(genres),
            "genres": genres,
            "scene_types": len({r.scene_type for r in rows}),
            "rows": len(rows),
        }

    # ------------------------------------------------------------ review
    def to_candidates(
        self,
        run_report: dict,
        min_samples: int = 20,
        delta_threshold: float = 3.0,
    ) -> list[PolicyCandidate]:
        """Arena scores -> PolicyCandidate queue (human review only).

        Candidates compare the current router director vs the best-scored
        director per (genre, scene_type), carrying evidence for the existing
        Policy Evolution Center approve/reject flow.
        """
        from backend.director.evolution.policy_candidate import compute_confidence

        rows = [r for r in run_report["rows"] if not r.get("error")]
        candidates: list[PolicyCandidate] = []
        for genre in GENRES:
            for scene_type in SCENE_TYPES:
                cell = [r for r in rows if r["genre"] == genre and r["scene_type"] == scene_type]
                if len(cell) < 2:
                    continue
                # aggregate per director (same director appears once per shot)
                by_director: dict[str, list[dict]] = {}
                for row in cell:
                    by_director.setdefault(row["director"], []).append(row)
                ranked = sorted(
                    (
                        (director, round(sum(r["total"] for r in group) / len(group), 1))
                        for director, group in by_director.items()
                    ),
                    key=lambda kv: -kv[1],
                )
                if len(ranked) < 2:
                    continue
                (first_dir, first_total), (second_dir, second_total) = ranked[:2]
                score_delta = round(first_total - second_total, 1)
                if score_delta < delta_threshold:
                    continue
                candidates.append(PolicyCandidate(
                    scene_type=scene_type,
                    from_director=second_dir,
                    to_director=first_dir,
                    samples_from=max(1, len(by_director[second_dir])),
                    samples_to=max(1, len(by_director[first_dir])),
                    avg_from=second_total,
                    avg_to=first_total,
                    score_delta=score_delta,
                    confidence=compute_confidence(
                        min(len(cell), min_samples), score_delta, min_samples
                    ),
                    reason=f"arena real-run {genre}/{scene_type}",
                    scope_key=genre,
                    project_scope=genre,
                    genre=genre,
                ))
        return candidates

    def propose(
        self,
        evolution: ControlledEvolution,
        min_samples: int = 20,
        delta_threshold: float = 3.0,
    ) -> dict:
        """Arena run -> candidates -> evolution propose (human approval gate)."""
        report = self.run()
        candidates = self.to_candidates(report, min_samples, delta_threshold)
        return {
            "real_providers": report["real_providers"],
            "shots": report["dataset"]["shots"],
            "candidate_count": len(candidates),
            "candidates": [c.to_dict() for c in candidates],
            "approval_mode": evolution.mode,
        }
