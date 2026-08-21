"""Config-driven Director Router (Phase 10.8-C Step 3).

Loads backend/director/router_policy.yaml so the route table can be tuned
(and later self-learned by Phase 11) without code changes.

Policy values:
- rule   -> RuleDirectorProvider (motion-heavy, deterministic)
- qwen   -> LLM director (emotion/narrative); validator fallback to rule
- hybrid -> LLM with rule fallback (world/exploration scenes)

The route table also drives the benchmark mixture evaluation (recombining
already-generated manifests, no extra LLM calls).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from backend.agents.director_v2 import ShotDirective
from backend.director.hybrid import HybridDirector
from backend.director.memory import DirectorMemory
from backend.director.providers import DirectorProvider, RuleDirectorProvider
from backend.director.validator import ShotValidator
from backend.story.models import Shot

DEFAULT_POLICY_PATH = Path(__file__).parent / "router_policy.yaml"


class DirectorRouter:
    """Route each shot to a director strategy from the policy table."""

    def __init__(self, policy_path: str | Path = DEFAULT_POLICY_PATH):
        self.policy_path = Path(policy_path)
        self.routes: dict[str, str] = {}
        self.default = "hybrid"
        self.version = "1.0"
        self.policy_learning: dict = {}
        self._load()

    def _load(self) -> None:
        if not self.policy_path.exists():
            raise FileNotFoundError(f"router policy missing: {self.policy_path}")
        data = yaml.safe_load(self.policy_path.read_text(encoding="utf-8")) or {}
        self.routes = {str(k).lower(): str(v) for k, v in (data.get("routes") or {}).items()}
        self.default = str(data.get("default") or "hybrid")
        self.version = str(data.get("version") or "1.0")
        self.policy_learning = dict(data.get("policy_learning") or {})

    def route_for(self, scene_type: str) -> str:
        return self.routes.get(str(scene_type or "").lower(), self.default)

    def route_counts(self, scene_types: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for scene_type in scene_types:
            key = self.route_for(scene_type)
            counts[key] = counts.get(key, 0) + 1
        return counts


class PolicyDirector(HybridDirector):
    """HybridDirector that routes each shot by the configurable policy."""

    def __init__(
        self,
        rule_provider: DirectorProvider | None = None,
        llm_provider: DirectorProvider | None = None,
        validator: ShotValidator | None = None,
        policy_path: str | Path = DEFAULT_POLICY_PATH,
        memory_root: str | Path | None = None,
    ):
        super().__init__(rule_provider=rule_provider, llm_provider=llm_provider, validator=validator)
        self.router = DirectorRouter(policy_path)
        self.routed: dict[str, int] = {}
        # Phase 11.1: every decision + outcome is recorded when a root is given.
        self.memory = DirectorMemory(memory_root) if memory_root is not None else None

    def _remember(
        self,
        shot: Shot,
        scene_type: str,
        route: str,
        directive: ShotDirective,
        section_context: dict | None = None,
    ) -> None:
        if self.memory is None:
            return
        director = directive.director_version or route
        self.memory.record_decision(
            shot_id=shot.id,
            director=director,
            scene_type=scene_type,
            shot_type=shot.shot_type,
            intent=directive.shot_intent,
            camera=directive.camera,
            lighting=directive.lighting,
            emotion_curve=directive.emotion_curve,
            project_id=str((section_context or {}).get("project_id") or ""),
            episode=str((section_context or {}).get("episode") or ""),
            genre=str((section_context or {}).get("genre") or ""),
            style=str((section_context or {}).get("style") or ""),
            character_universe=str((section_context or {}).get("character_universe") or ""),
        )
        # LLM route that ended on the rule provider: record the failure so
        # Phase 11.3 can down-weight that (scene_type, director) pair.
        if route != "rule" and director != route:
            self.memory.record_failure(
                shot.id, route, "llm_fallback",
                detail="validator_reject_or_provider_error",
            )

    def plan_shot(self, shot: Shot, section_context: dict | None = None) -> ShotDirective:
        section_context = section_context or {}
        scene_type = str(section_context.get("scene_type") or shot.shot_type or "")
        route = self.router.route_for(scene_type)
        self.routed[route] = self.routed.get(route, 0) + 1
        if route == "rule" or not self.llm_available:
            self.stats["rule_fallback"] += 1
            directive = self.rule.generate_directive(shot, section_context)
            self._remember(shot, scene_type, route, directive, section_context)
            return directive
        # qwen / hybrid: LLM with validator fallback to rule
        directive = super().plan_shot(shot, section_context)
        self._remember(shot, scene_type, route, directive, section_context)
        return directive

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
        """Feed post-generation quality back (Identity/Quality Gate, Vision Critic, human)."""
        if self.memory is not None:
            self.memory.record_quality(
                shot_id, quality_score, feedback,
                production_cost=production_cost,
                generation_time=generation_time,
                human_score=human_score,
                revision_count=revision_count,
                final_approved=final_approved,
            )

    def apply_memory_feedback(self, directive: ShotDirective) -> ShotDirective:
        """Phase 11.2 (GPT constraint 1): apply the previous shot's Vision Critic
        feedback as deterministic adjustments to this directive.

        The critic never edits directives; the director reads
        ``DirectorMemory.adjustments_for(previous_shot)`` and applies emotion
        scaling, camera-movement avoidance, lighting fixes, and records a
        ``memory_feedback`` note in continuity so every decision is traceable.
        """
        if self.memory is None:
            return directive
        previous_shot = (directive.continuity or {}).get("previous_shot")
        if not previous_shot:
            return directive
        adjustments = self.memory.adjustments_for(previous_shot)
        if not adjustments:
            return directive
        directive.continuity = dict(directive.continuity or {})
        scale = adjustments.get("emotion_scale")
        if scale is not None:
            for point in directive.emotion_curve or []:
                if isinstance(point, dict) and isinstance(point.get("intensity"), (int, float)):
                    point["intensity"] = round(
                        max(0.05, min(1.0, float(point["intensity"]) * float(scale))), 2
                    )
        avoid = adjustments.get("avoid_movements") or []
        if directive.camera.get("movement") in avoid:
            directive.camera["movement"] = adjustments.get("replacement_movement", "static")
        if adjustments.get("lighting_fix"):
            directive.lighting["style"] = adjustments["lighting_fix"]
        note = adjustments.get("note", "")
        if note:
            directive.continuity["memory_feedback"] = note
            if note not in directive.rationale:
                directive.rationale = (directive.rationale + " | memory_feedback:" + note).strip()
        return directive

    def plan_sequence(
        self,
        shots: list[Shot],
        sections: list | None = None,
    ) -> list[ShotDirective]:
        """Plan a shot list, threading previous_shot continuity AND applying the
        stored Vision Critic feedback of each previous shot to the next one."""
        directives = super().plan_sequence(shots, sections)
        if self.memory is not None:
            for directive in directives:
                self.apply_memory_feedback(directive)
        return directives
