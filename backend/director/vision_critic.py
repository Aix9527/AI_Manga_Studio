"""Vision Critic service (Phase 11.2, GPT approved).

Loop per GPT::

    Director -> Generate -> Vision Critic -> Feedback
        -> Director Memory -> Next Shot

The critic aggregates evidence from the existing gates:

- Quality Gate (``backend.video.quality_gate``): mosaic / block artifacts /
  exposure / temporal consistency / motion curve (static, flicker, blur)
- Identity Gate (``backend.video.identity_gate``): per-character presence
- Directive rule checks (deterministic, no video required): emotion curve
  intensity vs shot intent, camera physics

Constraint 1 (GPT): the critic NEVER mutates the directive. It only emits a
:class:`VisionCriticResult` whose feedback is written to Director Memory; the
next shot is optimized by :meth:`PolicyDirector.apply_memory_feedback`.

Constraint 2 (GPT): every finding is a :class:`VisionFeedback` with a fixed
category + severity + suggestion (see ``memory/feedback_schema.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from backend.agents.director_v2 import ShotDirective
from backend.director.memory.feedback_schema import (
    VisionFeedback,
    feedback_from_issue,
)
from backend.story.models import Shot

EMOTION_TOO_STRONG_AT = 0.95
EMOTION_TOO_WEAK_AT = 0.2


@dataclass
class VisionCriticResult:
    """Structured critic output (Feedback Object, GPT 11.2)."""

    shot_id: str
    quality_score: float = 0.0                      # 0-100, higher is better
    feedback: list[VisionFeedback] = field(default_factory=list)
    gate_reports: dict = field(default_factory=dict)
    passed: bool = True

    @property
    def has_problems(self) -> bool:
        return len(self.feedback) > 0

    def to_feedback_dict(self) -> dict:
        """Memory-compatible feedback payload (written via record_quality)."""
        return {
            "quality_score": round(self.quality_score, 1),
            "items": [f.to_dict() for f in self.feedback],
        }


class VisionCritic:
    """Aggregates Quality Gate + Identity Gate + directive rule checks."""

    def __init__(
        self,
        quality_checker: Callable[[Path, Any], Any] | None = None,
        identity_verifier: Any | None = None,
    ):
        # ``quality_checker(video_path, workdir) -> QualityReport`` (0-100 score)
        self.quality_checker = quality_checker
        # object with ``verify_video(video_path, references, workdir) -> IdentityGateReport``
        self.identity_verifier = identity_verifier

    # ------------------------------------------------------------------ API
    def critique(
        self,
        shot: Shot,
        directive: ShotDirective,
        *,
        video_path: str | Path | None = None,
        references: dict | None = None,
        workdir: str | Path | None = None,
        quality_report: Any | None = None,
        identity_report: Any | None = None,
    ) -> VisionCriticResult:
        """Assess one generated shot; never modifies ``directive``."""
        feedback: list[VisionFeedback] = []
        gate_reports: dict = {}

        # 1) deterministic directive rule checks
        feedback.extend(self._directive_checks(shot, directive))

        # 2) Quality Gate (injected report wins over live run)
        quality = quality_report
        if quality is None and video_path is not None and self.quality_checker is not None:
            quality = self.quality_checker(Path(video_path), workdir)
        if quality is not None:
            gate_reports["quality"] = self._quality_summary(quality)
            feedback.extend(self._quality_feedback(shot.id, quality))

        # 3) Identity Gate (injected report wins over live run)
        identity = identity_report
        if (
            identity is None
            and video_path is not None
            and references
            and self.identity_verifier is not None
        ):
            identity = self.identity_verifier.verify_video(
                Path(video_path), references, workdir=workdir
            )
        if identity is not None:
            gate_reports["identity"] = self._identity_summary(identity)
            feedback.extend(self._identity_feedback(shot.id, identity))

        score = self._score(quality, identity, feedback)
        passed = score >= 60.0 and not any(
            f.severity == "high" and f.category in ("physics", "character_identity")
            for f in feedback
        )
        return VisionCriticResult(
            shot_id=shot.id,
            quality_score=round(score, 1),
            feedback=feedback,
            gate_reports=gate_reports,
            passed=passed,
        )

    # ------------------------------------------------------- rule checks
    def _directive_checks(self, shot: Shot, directive: ShotDirective) -> list[VisionFeedback]:
        feedback: list[VisionFeedback] = []
        curve = list(directive.emotion_curve or [])
        if curve and shot.emotion:
            peak = max(float(p.get("intensity", 0.0)) for p in curve if isinstance(p, dict))
            if peak >= EMOTION_TOO_STRONG_AT:
                feedback.append(feedback_from_issue(
                    shot.id, "emotion_too_strong", source="rule_check",
                    detail={"peak_intensity": peak, "shot_emotion": shot.emotion},
                ))
            elif peak <= EMOTION_TOO_WEAK_AT:
                feedback.append(feedback_from_issue(
                    shot.id, "emotion_too_weak", source="rule_check",
                    detail={"peak_intensity": peak, "shot_emotion": shot.emotion},
                ))
        # camera physics: orbit/crane at extreme-close-up is impossible
        camera = directive.camera or {}
        movement = str(camera.get("movement", ""))
        distance = str(camera.get("distance", ""))
        if movement in ("orbit", "crane") and distance == "extreme-close-up":
            feedback.append(feedback_from_issue(
                shot.id, "camera_physics", source="rule_check",
                detail={"movement": movement, "distance": distance},
            ))
        return feedback

    # ------------------------------------------------------- quality gate
    def _quality_feedback(self, shot_id: str, report: Any) -> list[VisionFeedback]:
        feedback: list[VisionFeedback] = []
        suggestions = list(getattr(report, "recommendations", []) or [])
        for issue in list(getattr(report, "issues", []) or []):
            if issue == "missing_file":
                continue
            suggestion = suggestions[0] if suggestions else None
            detail = {}
            for metric in ("mean_frame_diff", "static_frame_ratio", "motion_score", "motion_cv",
                           "temporal_consistency", "overall_score"):
                value = getattr(report, metric, None)
                if isinstance(value, (int, float)):
                    detail[metric] = round(float(value), 4)
            feedback.append(feedback_from_issue(
                shot_id, str(issue), source="quality_gate",
                suggestion=suggestion, detail=detail,
            ))
        return feedback

    def _quality_summary(self, report: Any) -> dict:
        return {
            "overall_score": round(float(getattr(report, "overall_score", 0.0) or 0.0), 1),
            "passed": bool(getattr(report, "passed", False)),
            "issues": list(getattr(report, "issues", []) or []),
            "motion_cv": getattr(report, "motion_cv", 0.0),
            "static_frame_ratio": getattr(report, "static_frame_ratio", 0.0),
        }

    # ------------------------------------------------------ identity gate
    def _identity_feedback(self, shot_id: str, report: Any) -> list[VisionFeedback]:
        feedback: list[VisionFeedback] = []
        per_character = getattr(report, "per_character", {}) or {}
        for cid, verdict in per_character.items():
            if isinstance(verdict, dict) and verdict.get("verdict") == "fail":
                ratio = float(verdict.get("presence_ratio", 0.0))
                issue = "character_missing" if ratio <= 0.0 else "character_drift"
                feedback.append(feedback_from_issue(
                    shot_id, issue, source="identity_gate",
                    detail={"character_id": cid, "presence_ratio": round(ratio, 3)},
                ))
        return feedback

    def _identity_summary(self, report: Any) -> dict:
        per_character = getattr(report, "per_character", {}) or {}
        return {
            "overall_verdict": getattr(report, "overall_verdict", "pass"),
            "per_character": {
                cid: v.get("verdict") if isinstance(v, dict) else str(v)
                for cid, v in per_character.items()
            },
        }

    # ------------------------------------------------------------- score
    def _score(self, quality: Any, identity: Any, feedback: list[VisionFeedback]) -> float:
        base = 100.0
        if quality is not None:
            base = float(getattr(quality, "overall_score", 100.0) or 100.0)
        for item in feedback:
            base -= item.penalty()
        # identity failures are decisive: one failure must fail the shot
        identity_fails = sum(
            1 for f in feedback if f.category == "character_identity" and f.severity == "high"
        )
        base -= 25.0 * identity_fails
        return max(0.0, min(100.0, base))
