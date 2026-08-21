"""Hybrid Director router (Phase 10.7-B).

Diagram per GPT approval::

    Story Memory
         |
    Director Router
       /        \
Rule Director    LLM Director
       \        /
    Shot Validator
         |
    ShotDirective -> Pipeline

The router tries the LLM provider for every shot, validates the result with
the deterministic :class:`ShotValidator`, and falls back to the rule provider
on any failure (invalid JSON, missing fields, impossible camera physics...).
``rule-v2`` is never replaced: it is the permanent fallback and the baseline.
"""

from __future__ import annotations

from typing import Any

from backend.agents.director_v2 import ShotDirective
from backend.director.providers.base import DirectorProvider, ProviderError
from backend.director.providers.rule_provider import RuleDirectorProvider
from backend.director.validator import ShotValidator, ValidationReport
from backend.story.models import Shot


def section_context_for(section: Any) -> dict:
    """Build the context dict the rule/LLM providers expect from a StorySection."""
    if section is None:
        return {}
    if isinstance(section, dict):
        return {
            "character_state": section.get("character_state") or {},
            "visual_theme": section.get("visual_theme") or {},
            "emotion": section.get("emotion") or "",
        }
    return {
        "character_state": getattr(section, "character_state", None) or {},
        "visual_theme": getattr(section, "visual_theme", None) or {},
        "emotion": getattr(section, "emotion", None) or "",
    }


class HybridDirector:
    """Routes each shot through LLM -> validator -> rule fallback."""

    def __init__(
        self,
        rule_provider: DirectorProvider | None = None,
        llm_provider: DirectorProvider | None = None,
        validator: ShotValidator | None = None,
    ):
        self.rule = rule_provider or RuleDirectorProvider()
        self.llm = llm_provider
        self.validator = validator or ShotValidator()
        self.stats = {"llm_used": 0, "llm_failed": 0, "rule_fallback": 0}

    @property
    def llm_available(self) -> bool:
        if self.llm is None:
            return False
        return bool(getattr(self.llm, "is_available", True))

    def plan_shot(self, shot: Shot, section_context: dict | None = None) -> ShotDirective:
        if self.llm_available:
            try:
                directive = self.llm.generate_directive(shot, section_context)
                report = self.validator.validate(directive, shot, section_context)
                if report.ok:
                    self.stats["llm_used"] += 1
                    return directive
                self.stats["llm_failed"] += 1
            except ProviderError:
                self.stats["llm_failed"] += 1
        self.stats["rule_fallback"] += 1
        return self.rule.generate_directive(shot, section_context)

    def plan_sequence(
        self,
        shots: list[Shot],
        sections: list | None = None,
    ) -> list[ShotDirective]:
        """Plan a shot list with previous_shot threading + sequence validation.

        Mirrors ``DirectorV2Agent.plan_sequence`` so the bridge contract is
        unchanged; returns validated directives and records the report.
        """
        sections = sections or []
        section_by_scene = {getattr(s, "scene_id", ""): s for s in sections}
        directives: list[ShotDirective] = []
        prev_id = ""
        for shot in shots:
            ctx = section_context_for(section_by_scene.get(shot.scene_id, ""))
            directive = self.plan_shot(shot, ctx)
            directive.continuity = dict(directive.continuity or {})
            directive.continuity["previous_shot"] = prev_id
            directives.append(directive)
            prev_id = shot.id
        self.last_sequence_report: ValidationReport = self.validator.validate_sequence(directives, shots)
        return directives
