"""Narrative Director (Phase 12.8 council member).

Focus: story logic, character motivation, pacing.  Weight 25% (GPT spec).
Blends the arena narrative component with the director's overall quality
strength so the vote reflects narrative AND craft, not just one signal.
"""

from __future__ import annotations

from backend.director.arena import DIRECTOR_STRENGTH
from backend.director.council.base import CouncilAgent


class NarrativeDirector(CouncilAgent):
    name = "narrative"
    weight = 0.25

    def score(self, row: dict) -> float:
        components = row.get("components") or {}
        narrative = float(components.get("narrative") or 0.0)
        quality = float(components.get("quality") or 0.0)
        return 0.7 * narrative + 0.3 * quality
