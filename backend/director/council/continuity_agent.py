"""Continuity Director (Phase 12.8 council member).

Focus: character consistency, spatial continuity, asset inheritance.
Weight 20%.  Blends continuity/stability with craft quality.
"""

from __future__ import annotations

from backend.director.council.base import CouncilAgent


class ContinuityDirector(CouncilAgent):
    name = "continuity"
    weight = 0.20

    def score(self, row: dict) -> float:
        components = row.get("components") or {}
        continuity = float(components.get("continuity") or 0.0)
        stability = float(components.get("stability") or 0.0)
        quality = float(components.get("quality") or 0.0)
        return 0.5 * continuity + 0.2 * stability + 0.3 * quality
