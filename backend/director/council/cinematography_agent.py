"""Cinematography Director (Phase 12.8 council member).

Focus: camera language, motion, composition, lighting.  Weight 20%.
Blends camera component with craft quality; the tie-breaker is the
director's overall strength so a camera vote is never a coin flip.
"""

from __future__ import annotations

from backend.director.council.base import CouncilAgent


class CinematographyDirector(CouncilAgent):
    name = "camera"
    weight = 0.20

    def score(self, row: dict) -> float:
        components = row.get("components") or {}
        camera = float(components.get("camera") or 0.0)
        quality = float(components.get("quality") or 0.0)
        return 0.7 * camera + 0.3 * quality
