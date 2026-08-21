"""Unified Vision Critic feedback schema (Phase 11.2, GPT constraint 2).

Every critic (Quality Gate / Identity Gate / Motion CV / directive rule
checks) emits :class:`VisionFeedback` with a fixed ``category``, ``severity``
and ``suggestion`` so Phase 11.3 can learn from comparable signals instead of
free-form text.

GPT-specified shape::

    {
      "category": [
        "character_identity", "motion", "composition",
        "lighting", "emotion", "physics", "continuity"
      ],
      "severity": "low|medium|high",
      "suggestion": "..."
    }
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

FEEDBACK_CATEGORIES = [
    "character_identity",
    "motion",
    "composition",
    "lighting",
    "emotion",
    "physics",
    "continuity",
]
SEVERITY_LEVELS = ("low", "medium", "high")

# issue keyword -> (category, default severity, default suggestion)
ISSUE_MAP: dict[str, tuple[str, str, str]] = {
    # Quality Gate (video)
    "mosaic": ("physics", "high", "Reduce denoise strength and increase steps"),
    "block_artifact": ("physics", "high", "Increase resolution or use super-resolution"),
    "flickering": ("physics", "high", "Improve temporal consistency (lower CFG)"),
    "static_video": ("motion", "high", "Add explicit motion tokens; ban still-frame wording"),
    "low_motion": ("motion", "medium", "Bump character/camera motion level"),
    "low_motion_flow": ("motion", "medium", "Increase optical-flow amplitude"),
    "flicker_motion_curve": ("motion", "high", "Reduce camera shake / urgent motion tokens"),
    "motion_blur": ("motion", "medium", "Reduce motion intensity in prompt"),
    "too_dark": ("lighting", "medium", "Add brightness to prompt (well-lit, bright)"),
    "too_bright": ("lighting", "medium", "Reduce overexposure in prompt"),
    "low_quality": ("composition", "medium", "Re-generate with adjusted parameters"),
    # Identity Gate
    "character_drift": ("character_identity", "high", "Strengthen character lock with reference frames"),
    "character_missing": ("character_identity", "high", "Re-insert the missing character into composition"),
    # Directive rule checks (no video needed)
    "emotion_too_strong": ("emotion", "medium", "reduce_expression_level"),
    "emotion_too_weak": ("emotion", "low", "increase_expression_level"),
    "camera_physics": ("physics", "medium", "Use a physically plausible camera combination"),
    "missing_continuity": ("continuity", "low", "Thread previous_shot continuity constraints"),
    "composition_imbalance": ("composition", "low", "Re-balance framing (rule of thirds)"),
}

SEVERITY_PENALTY = {"high": 20.0, "medium": 10.0, "low": 5.0}


def feedback_from_issue(
    shot_id: str,
    issue: str,
    *,
    source: str = "vision_critic",
    suggestion: str | None = None,
    detail: dict | None = None,
) -> "VisionFeedback":
    """Build a :class:`VisionFeedback` from an issue keyword."""
    category, severity, default_suggestion = ISSUE_MAP.get(
        issue, ("physics", "low", "Review and regenerate")
    )
    return VisionFeedback(
        shot_id=shot_id,
        category=category,
        severity=severity,
        issue=issue,
        suggestion=suggestion or default_suggestion,
        source=source,
        detail=detail or {},
    )


@dataclass
class VisionFeedback:
    """One structured critic finding (GPT 11.2 schema)."""

    shot_id: str = ""
    category: str = "physics"          # one of FEEDBACK_CATEGORIES
    severity: str = "low"              # low | medium | high
    issue: str = ""                    # stable keyword, see ISSUE_MAP
    suggestion: str = ""               # actionable next-policy hint
    source: str = "vision_critic"      # quality_gate | identity_gate | motion_cv | rule_check | human
    detail: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        return asdict(self)

    def validate(self) -> bool:
        return self.category in FEEDBACK_CATEGORIES and self.severity in SEVERITY_LEVELS

    def penalty(self) -> float:
        return SEVERITY_PENALTY.get(self.severity, 0.0)
