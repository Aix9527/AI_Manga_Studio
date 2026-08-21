"""Policy analyzer (Phase 11.3-A, GPT design).

Reads Director Memory's per-(scene_type, director) quality stats, compares
them with the currently deployed router policy, and proposes candidate
changes (e.g. ``action: rule -> hybrid``) WITHOUT executing them.
"""

from __future__ import annotations

from backend.director.evolution.policy_candidate import (
    MIN_DELTA_THRESHOLD,
    PolicyCandidate,
    compute_confidence,
)
from backend.director.memory import PolicyMemory
from backend.director.policy_router import DirectorRouter

# route -> the director that actually produces shots on that route
ROUTE_DIRECTOR = {"rule": "rule-v2", "qwen": "llm-qwen", "hybrid": "llm-qwen"}
# director -> route to write into the policy YAML when a candidate is approved
DIRECTOR_ROUTE = {
    "rule-v2": "rule",
    "llm-qwen": "qwen",
    "llm-openai": "qwen",
    "llm-claude": "qwen",
    "mixture": "hybrid",
}


class PolicyAnalyzer:
    """Discovers optimization opportunities from real memory statistics."""

    def __init__(self, policy_memory: PolicyMemory, router: DirectorRouter):
        self.memory = policy_memory
        self.router = router

    def analyze(
        self,
        min_samples: int | None = None,
        delta_threshold: float = MIN_DELTA_THRESHOLD,
        confidence_threshold: float | None = None,
    ) -> list[PolicyCandidate]:
        config = self.router.policy_learning or {}
        min_samples = min_samples or int(config.get("min_samples") or 20)
        confidence_threshold = confidence_threshold or float(
            config.get("confidence_threshold") or 0.85
        )
        # Phase 12.3: candidates are computed inside one memory scope so a
        # sci-fi project's experience can never vote for a historical one.
        rows_by_cell: dict[tuple, list[dict]] = {}
        for row in self.memory.stats():
            scope_key = str(row.get("scope_key") or "")
            rows_by_cell.setdefault((scope_key, row["scene_type"]), []).append(row)

        candidates: list[PolicyCandidate] = []
        for (scope_key, scene_type), rows in rows_by_cell.items():
            current_route = self.router.route_for(scene_type)
            current_director = ROUTE_DIRECTOR.get(current_route, "rule-v2")
            current = next((r for r in rows if r["director"] == current_director), None)
            if not current or current["shots"] < min_samples or current["avg_quality"] is None:
                continue
            alternatives = [
                r for r in rows
                if r["director"] != current_director
                and r["shots"] >= min_samples
                and r["avg_quality"] is not None
            ]
            if not alternatives:
                continue
            best = max(alternatives, key=lambda r: r["avg_quality"])
            score_delta = round(best["avg_quality"] - current["avg_quality"], 1)
            if score_delta < delta_threshold:
                continue
            candidates.append(PolicyCandidate(
                scene_type=scene_type,
                from_director=current_director,
                to_director=best["director"],
                samples_from=current["shots"],
                samples_to=best["shots"],
                avg_from=current["avg_quality"],
                avg_to=best["avg_quality"],
                score_delta=score_delta,
                confidence=compute_confidence(best["shots"], score_delta, min_samples),
                reason=f"route={current_route} avg {current['avg_quality']} -> {best['avg_quality']}",
                scope_key=scope_key,
                project_scope=str(current.get("project_scope") or ""),
                genre=str(current.get("genre") or ""),
                style=str(current.get("style") or ""),
            ))
        return sorted(candidates, key=lambda c: -c.score_delta)
