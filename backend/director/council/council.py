"""Director Council (Phase 12.8, GPT spec).

Multi-agent decision layer between the Arena and the Policy Candidate queue::

    Arena -> Council -> Policy Candidate -> Human Approval -> Router

Five expert agents vote per shot with GPT-specified weights::

    Narrative 25% | Cinematography 20% | Continuity 20% | Production 15% | Risk Critic 20%

The final winner is the weighted vote winner.  The **Council Decision Score**
is a separate score that blends the arena quality with the project goal
(genre), so cost never dominates creative intent.  Arena raw scores are NOT
modified (GPT constraint).  Every decision is explainable (per-agent reason)
and flows to the human approval chain — never auto-deployed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.director.arena import GENRES
from backend.director.council.base import CouncilAgent, CouncilDecision, CouncilVote
from backend.director.council.cinematography_agent import CinematographyDirector
from backend.director.council.continuity_agent import ContinuityDirector
from backend.director.council.critic_agent import RiskCritic
from backend.director.council.narrative_agent import NarrativeDirector
from backend.director.council.production_agent import ProductionDirector

# GPT Phase 12.8 spec
COUNCIL_WEIGHTS = {
    "narrative": 0.25,
    "camera": 0.20,
    "continuity": 0.20,
    "production": 0.15,
    "critic": 0.20,
}

# genre -> goal emphasis for the Council Decision Score (creative intent boost)
GENRE_GOAL_BOOST = {
    "科幻": {"narrative": 0.05, "production": -0.05},
    "古装": {"continuity": 0.05, "production": -0.05},
    "动画": {"narrative": 0.03, "camera": 0.02},
    "都市": {"critic": 0.03, "production": 0.02},
}


@dataclass
class CouncilSummary:
    decisions: list[CouncilDecision]
    winners: dict[str, int]                 # director -> count
    explainable: int                        # decisions with per-agent reasons
    coverage: dict
    agents: list[str]

    def to_dict(self) -> dict:
        return {
            "decisions": [d.to_dict() for d in self.decisions],
            "winners": self.winners,
            "explainable": self.explainable,
            "coverage": self.coverage,
            "agents": self.agents,
        }


class DirectorCouncil:
    """Aggregates the five council agents into per-shot weighted decisions."""

    def __init__(self, agents: list[CouncilAgent] | None = None):
        self.agents = agents or self._default_agents()
        total = sum(a.weight for a in self.agents)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"council weights must sum to 1.0, got {total}")

    @staticmethod
    def _default_agents() -> list[CouncilAgent]:
        return [
            NarrativeDirector(),
            CinematographyDirector(),
            ContinuityDirector(),
            ProductionDirector(),
            RiskCritic(),
        ]

    def agent_names(self) -> list[str]:
        return [a.name for a in self.agents]

    # ------------------------------------------------------------ voting
    def decide_shot(
        self,
        shot_id: str,
        rows: list[dict],
        genre: str = "",
    ) -> CouncilDecision:
        """Weighted council vote for one shot (rows = all director rows)."""
        candidates = sorted({r["director"] for r in rows})
        votes: list[CouncilVote] = []
        for agent in self.agents:
            votes.append(agent.vote(shot_id, rows))

        weighted: dict[str, float] = {}
        for vote in votes:
            weighted[vote.candidate] = weighted.get(vote.candidate, 0.0) + vote.weight * vote.score
        winner = max(weighted, key=lambda d: weighted[d])
        # confidence: weighted agreement between top-2
        ranked = sorted(weighted.items(), key=lambda kv: -kv[1])
        top, second = ranked[0][1], (ranked[1][1] if len(ranked) > 1 else 0.0)
        confidence = min(0.99, 0.5 + (top - second))
        reasons = [v.reason for v in votes if v.candidate == winner]
        return CouncilDecision(
            shot_id=shot_id,
            candidates=candidates,
            votes=votes,
            winner=winner,
            confidence=round(confidence, 3),
            reasons=reasons,
            scope_key=genre,
        )

    def council_decision_score(
        self,
        decision: CouncilDecision,
        genre: str = "",
    ) -> dict:
        """Separate Council Decision Score (project-goal aware).

        Blends the weighted vote winner's raw arena total with a small
        genre-goal boost so cost never suppresses creative intent.  Arena
        raw scores are untouched.
        """
        winner_vote = next(
            (v for v in decision.votes if v.candidate == decision.winner), None
        )
        if winner_vote is None:
            return {"score": 0.0, "boost": 0.0, "genre": genre}
        base = winner_vote.score * 100.0
        boosts = GENRE_GOAL_BOOST.get(genre, {})
        boost = sum(boosts.get(v.agent, 0.0) for v in decision.votes if v.candidate == decision.winner)
        score = round(base + boost * 100.0 * decision.confidence, 1)
        return {"score": score, "boost": round(boost, 3), "genre": genre}

    # --------------------------------------------------------- candidates
    def to_candidates(
        self,
        summary: CouncilSummary,
        arena_report: dict,
        min_confidence: float = 0.5,
    ) -> list:
        """Council decisions -> PolicyCandidate queue (human approval only).

        One candidate per (genre, scene_type) cell: the council winner vs the
        current static router director, carrying the council confidence and
        explainable reasons.  Nothing is applied automatically.
        """
        from backend.director.evolution.policy_candidate import (
            PolicyCandidate,
            compute_confidence,
        )

        rows = arena_report.get("rows") or []
        cells: dict[tuple, dict] = {}
        for decision in summary.decisions:
            genre = decision.scope_key
            shot_rows = [r for r in rows if r["shot_id"] == decision.shot_id]
            scene_type = shot_rows[0].get("scene_type", "") if shot_rows else ""
            if not scene_type:
                continue
            key = (genre, scene_type)
            cells.setdefault(key, {"decisions": [], "count": 0})
            cells[key]["decisions"].append(decision)
            cells[key]["count"] += 1

        from backend.director.policy_router import DirectorRouter, DEFAULT_POLICY_PATH
        static = DirectorRouter(DEFAULT_POLICY_PATH)
        ROUTE_DIRECTOR = {"rule": "rule-v2", "qwen": "llm-qwen", "hybrid": "llm-qwen"}

        candidates = []
        for (genre, scene_type), cell in cells.items():
            if cell["count"] < 2:
                continue
            winner_counter: dict[str, int] = {}
            confidences: list[float] = []
            for decision in cell["decisions"]:
                winner_counter[decision.winner] = winner_counter.get(decision.winner, 0) + 1
                confidences.append(decision.confidence)
            winner = max(winner_counter, key=lambda d: winner_counter[d])
            current_route = static.route_for(scene_type)
            current = ROUTE_DIRECTOR.get(current_route, "rule-v2")
            if winner == current:
                continue
            avg_confidence = sum(confidences) / len(confidences)
            if avg_confidence < min_confidence:
                continue
            candidates.append(PolicyCandidate(
                scene_type=scene_type,
                from_director=current,
                to_director=winner,
                samples_from=cell["count"],
                samples_to=cell["count"],
                avg_from=80.0,
                avg_to=round(avg_confidence * 100.0, 1),
                score_delta=round((avg_confidence - 0.5) * 100.0, 1),
                confidence=round(min(0.99, avg_confidence), 2),
                reason=f"council {genre}/{scene_type} winner={winner} "
                       f"confidence={avg_confidence:.2f}",
                scope_key=genre,
                project_scope=genre,
                genre=genre,
            ))
        return sorted(candidates, key=lambda c: -c.score_delta)

    # ------------------------------------------------------------ runner
    def run(self, arena_report: dict) -> CouncilSummary:
        """Run the council over every shot in the arena report."""
        rows = arena_report.get("rows") or []
        by_shot: dict[str, list[dict]] = {}
        for row in rows:
            by_shot.setdefault(row["shot_id"], []).append(row)

        decisions: list[CouncilDecision] = []
        for shot_id, shot_rows in by_shot.items():
            genre = shot_rows[0].get("genre", "")
            decision = self.decide_shot(shot_id, shot_rows, genre)
            decisions.append(decision)

        winners: dict[str, int] = {}
        explainable = 0
        for decision in decisions:
            winners[decision.winner] = winners.get(decision.winner, 0) + 1
            if decision.reasons:
                explainable += 1

        return CouncilSummary(
            decisions=decisions,
            winners=winners,
            explainable=explainable,
            coverage={
                "shots": len(decisions),
                "genres": sorted({d.scope_key for d in decisions}),
                "scopes": len({d.scope_key for d in decisions}),
            },
            agents=self.agent_names(),
        )
