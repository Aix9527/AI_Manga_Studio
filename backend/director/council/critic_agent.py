"""Risk Critic (Phase 12.8 council member).

Focus: failure risk, physics errors, AI hallucinations.  Weight 20%.
Penalizes invalid directives and fallbacks; rewards stability, with a
small quality tie-breaker (higher craft = fewer hallucination risks).
"""

from __future__ import annotations

from backend.director.council.base import CouncilAgent


class RiskCritic(CouncilAgent):
    name = "critic"
    weight = 0.20

    def score(self, row: dict) -> float:
        components = row.get("components") or {}
        stability = float(components.get("stability") or 0.0)
        quality = float(components.get("quality") or 0.0)
        valid = 1.0 if row.get("valid") else 0.0
        fallback_penalty = 0.0 if row.get("fallback_count", 0) == 0 else -0.4
        return 0.4 * stability + 0.3 * valid + 0.3 * quality + fallback_penalty
