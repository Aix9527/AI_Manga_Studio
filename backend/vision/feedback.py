"""
Feedback — Sprint 7.1 Vision Critic.
Score → prompt rewrite feedback loop for self-improving generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from backend.vision.quality_score import QualityReport


@dataclass
class FeedbackAction:
    """A specific prompt modification action."""
    action_type: str = ""       # "add_tag", "remove_tag", "strengthen", "weaken",
                                # "fix_composition", "fix_camera", "fix_expression",
                                # "increase_steps", "add_negative"
    target: str = ""            # What to modify
    value: str = ""             # New/modified value
    reason: str = ""            # Why this action is suggested


@dataclass
class PromptFeedback:
    """Full feedback loop result: quality report → prompt rewrite."""
    shot_id: str = ""
    original_prompt: str = ""
    original_negative: str = ""
    rewritten_prompt: str = ""
    rewritten_negative: str = ""

    score_before: float = 0.0
    iteration: int = 0
    actions: list[FeedbackAction] = field(default_factory=list)

    # Metadata
    should_retry: bool = False
    max_retries: int = 2


class FeedbackLoop:
    """
    Self-improving feedback loop.

    Takes a QualityReport and original prompt, generates a
    rewritten prompt designed to fix the identified issues.
    """

    def __init__(self, max_retries: int = 2, score_threshold: float = 0.65):
        self.max_retries = max_retries
        self.threshold = score_threshold

    def generate_feedback(
        self,
        report: QualityReport,
        original_prompt: str,
        original_negative: str = "",
        iteration: int = 0,
    ) -> PromptFeedback:
        """
        Generate prompt rewrites from quality report.

        Returns a PromptFeedback with rewritten prompts if issues found.
        """
        fb = PromptFeedback(
            shot_id=report.shot_id,
            original_prompt=original_prompt,
            original_negative=original_negative,
            score_before=report.overall_score,
            iteration=iteration,
        )

        # Determine if retry is warranted
        if report.passed:
            fb.should_retry = False
            fb.rewritten_prompt = original_prompt
            fb.rewritten_negative = original_negative
            return fb

        if iteration >= self.max_retries:
            fb.should_retry = False
            fb.rewritten_prompt = original_prompt
            fb.rewritten_negative = original_negative
            return fb

        fb.should_retry = True

        # Generate actions from issues
        actions = self._diagnose_to_actions(report)
        fb.actions = actions

        # Apply actions to rewrite prompt
        fb.rewritten_prompt = self._apply_actions(original_prompt, actions)
        fb.rewritten_negative = self._enhance_negative(original_negative, actions, report)

        return fb

    def batch_feedback(
        self,
        reports: list[QualityReport],
        original_prompts: list[str],
        original_negatives: list[str] | None = None,
    ) -> list[PromptFeedback]:
        """Generate feedback for a batch of reports."""
        negatives = original_negatives or [""] * len(reports)
        return [
            self.generate_feedback(
                reports[i],
                original_prompts[i] if i < len(original_prompts) else "",
                negatives[i] if i < len(negatives) else "",
            )
            for i in range(len(reports))
        ]

    def should_continue(self, feedbacks: list[PromptFeedback]) -> bool:
        """Check if any feedback suggests retry."""
        return any(fb.should_retry for fb in feedbacks)

    # ── Action Generation ───────────────────────────────────────

    def _diagnose_to_actions(self, report: QualityReport) -> list[FeedbackAction]:
        actions: list[FeedbackAction] = []

        for issue in report.issues:
            if "Composition" in issue:
                actions.append(FeedbackAction(
                    action_type="fix_composition",
                    target="composition",
                    value="rule of thirds, balanced framing",
                    reason="Composition below threshold",
                ))
            elif "Style" in issue:
                actions.append(FeedbackAction(
                    action_type="add_tag",
                    target="style",
                    value="high quality manga art style, clean linework, professional illustration",
                    reason="Style consistency below threshold",
                ))
            elif "Character" in issue:
                actions.append(FeedbackAction(
                    action_type="strengthen",
                    target="character",
                    value="consistent character design, same face, same outfit",
                    reason="Character consistency below threshold",
                ))
            elif "Expression" in issue:
                actions.append(FeedbackAction(
                    action_type="fix_expression",
                    target="expression",
                    value="clear facial expression",
                    reason="Expression mismatch",
                ))
            elif "Camera" in issue:
                actions.append(FeedbackAction(
                    action_type="fix_camera",
                    target="camera",
                    value="specified camera angle, precise framing",
                    reason="Camera angle mismatch",
                ))
            elif "Technical" in issue:
                actions.append(FeedbackAction(
                    action_type="increase_steps",
                    target="quality",
                    value="high resolution, sharp focus, detailed",
                    reason="Technical quality below threshold",
                ))

        # Deduplicate actions by type
        seen = set()
        unique: list[FeedbackAction] = []
        for a in actions:
            if a.action_type not in seen:
                seen.add(a.action_type)
                unique.append(a)
        return unique

    # ── Prompt Rewriting ────────────────────────────────────────

    @staticmethod
    def _apply_actions(prompt: str, actions: list[FeedbackAction]) -> str:
        """Apply feedback actions to rewrite the positive prompt."""
        result = prompt

        for action in actions:
            if action.action_type == "fix_composition":
                if "composition" not in result.lower():
                    result = f"({action.value}), {result}"

            elif action.action_type == "add_tag":
                if action.value.lower() not in result.lower():
                    result = f"{result}, {action.value}"

            elif action.action_type == "strengthen":
                if action.value.lower() not in result.lower():
                    result = f"{result}, {action.value}"

            elif action.action_type == "fix_expression":
                if "expression" not in result.lower():
                    result = f"{result}, {action.value}"

            elif action.action_type == "fix_camera":
                if "camera" not in result.lower() and "angle" not in result.lower():
                    result = f"{result}, {action.value}"

            elif action.action_type == "increase_steps":
                if "high resolution" not in result.lower():
                    result = f"{result}, {action.value}"

        return result

    @staticmethod
    def _enhance_negative(
        negative: str,
        actions: list[FeedbackAction],
        report: QualityReport,
    ) -> str:
        """Enhance negative prompt based on quality issues."""
        enhancements: list[str] = []

        if report.technical_quality < 0.5:
            enhancements.append("blurry, low quality, artifacts, distorted")

        if report.composition_score < 0.5:
            enhancements.append("poor composition, bad framing, awkward pose")

        if report.style_consistency < 0.5:
            enhancements.append("inconsistent art style, mixed media, sketchy")

        if report.character_consistency < 0.5:
            enhancements.append("different face, mismatched features, wrong character")

        if enhancements:
            sep = ", " if negative else ""
            return f"{negative}{sep}{', '.join(enhancements)}"

        return negative
