"""Production Director (Phase 12.8 council member).

Focus: cost, time, GPU resources.  Weight 15% (GPT spec).
Pure production view: cost component (1 = cheapest) plus a fallback
penalty so an unstable director can never win on price alone.
"""

from __future__ import annotations

from backend.director.council.base import CouncilAgent


class ProductionDirector(CouncilAgent):
    name = "production"
    weight = 0.15

    def score(self, row: dict) -> float:
        components = row.get("components") or {}
        cost = float(components.get("cost") or 0.0)          # 1 = cheapest
        fallback_penalty = 0.0 if row.get("fallback_count", 0) == 0 else -0.3
        return cost + fallback_penalty
