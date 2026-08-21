"""Council agent base (Phase 12.8, GPT spec).

A :class:`CouncilAgent` is one expert director on the council.  Each agent
votes for a candidate director for one shot using ONLY its own specialty
signals, and always explains its vote.  Agents never edit directives and
never apply policy; the :class:`DirectorCouncil` aggregates weighted votes
into a final decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CouncilVote:
    """One agent's vote for a shot."""

    agent: str                    # narrative | camera | continuity | production | critic
    weight: float                 # council weight for this specialty
    candidate: str                # director voted for
    score: float                  # specialty score for that director
    confidence: float             # 0-1
    reason: str = ""              # explainable justification

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "weight": self.weight,
            "candidate": self.candidate,
            "score": round(self.score, 3),
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
        }


@dataclass
class CouncilDecision:
    """Final per-shot decision from the weighted council vote."""

    shot_id: str
    candidates: list[str]
    votes: list[CouncilVote]
    winner: str
    confidence: float
    reasons: list[str]
    scope_key: str = ""

    def to_dict(self) -> dict:
        return {
            "shot_id": self.shot_id,
            "candidates": self.candidates,
            "votes": [v.to_dict() for v in self.votes],
            "winner": self.winner,
            "confidence": round(self.confidence, 3),
            "reasons": self.reasons,
            "scope_key": self.scope_key,
        }


class CouncilAgent:
    """Base class: vote for the best candidate under one specialty."""

    name = "base"
    weight = 0.0

    def __init__(self) -> None:
        self.votes_cast = 0

    # ------------------------------------------------------------------
    def score(self, row: dict) -> float:
        """Specialty score for one (shot x director) arena row."""
        raise NotImplementedError

    def vote(
        self,
        shot_id: str,
        candidate_rows: list[dict],
    ) -> CouncilVote:
        """Pick the candidate with the best specialty score for this shot."""
        if not candidate_rows:
            raise ValueError(f"no candidate rows for shot {shot_id}")
        best = max(candidate_rows, key=lambda r: self.score(r))
        second = max(
            (r for r in candidate_rows if r["director"] != best["director"]),
            key=lambda r: self.score(r),
            default=None,
        )
        delta = self.score(best) - (self.score(second) if second else 0.0)
        confidence = min(0.99, 0.5 + abs(delta) * 0.5)
        self.votes_cast += 1
        return CouncilVote(
            agent=self.name,
            weight=self.weight,
            candidate=best["director"],
            score=self.score(best),
            confidence=round(confidence, 3),
            reason=f"{self.name} prefers {best['director']} "
                   f"(score {self.score(best):.3f} vs runner-up "
                   f"{self.score(second) if second else 0.0:.3f})",
        )
