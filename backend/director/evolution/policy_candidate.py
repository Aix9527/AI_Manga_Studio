"""Policy candidate (Phase 11.3-A, GPT design).

A :class:`PolicyCandidate` is a *suggested* router change that is never
applied automatically: it carries the evidence (sample counts, average
quality, score delta, confidence) that a human approval flow consumes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

MIN_DELTA_THRESHOLD = 3.0


def compute_confidence(n_samples: int, score_delta: float, min_samples: int = 20) -> float:
    """Confidence grows with sample count and observed score delta.

    Deterministic heuristic: 0.75 at exactly ``min_samples`` with a tiny
    delta, approaching 0.99 for large samples / large deltas.
    """
    n = max(n_samples, 1)
    strength = n / (n + max(min_samples, 1))
    base = 0.5 + 0.5 * strength
    delta_bonus = min(0.24, abs(score_delta) / 25.0)
    return round(min(0.99, base + delta_bonus), 2)


@dataclass
class PolicyCandidate:
    scene_type: str
    from_director: str
    to_director: str
    samples_from: int
    samples_to: int
    avg_from: float
    avg_to: float
    score_delta: float
    confidence: float
    reason: str = "avg_quality comparison"
    scope_key: str = ""                      # Phase 12.3 isolation prefix
    project_scope: str = ""
    genre: str = ""
    style: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        return asdict(self)

    def is_valid(self, min_samples: int = 20, confidence_threshold: float = 0.85) -> bool:
        return (
            self.samples_from >= min_samples
            and self.samples_to >= min_samples
            and self.score_delta >= MIN_DELTA_THRESHOLD
            and self.confidence >= confidence_threshold
        )


