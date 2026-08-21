"""Critic Agent — reviews production decisions for quality control."""

from __future__ import annotations

from typing import Optional


class CriticAgent:
    """
    Critic Agent — reviews Director's ShotBrief and provides quality feedback.

    Responsibilities:
    - Validate panel layout decisions
    - Check pacing rhythm
    - Detect character consistency issues
    - Flag visual storytelling problems
    """

    def __init__(self):
        self.rules = self._build_rulebook()

    def review_shot(self, brief) -> dict:
        """Review a ShotBrief and return feedback."""
        issues: list[str] = []

        shot = brief.shot

        # Rule 1: Panel layout validation
        layout_ok = self._check_layout(brief.panel_layout, shot.shot_type)
        if not layout_ok:
            issues.append(f"Panel layout '{brief.panel_layout}' may not suit shot type '{shot.shot_type}'")

        # Rule 2: Shot description length check
        if len(shot.description) < 20 and not shot.dialogue:
            issues.append("Shot description too short — may lack visual information")

        # Rule 3: Dialogue without character
        if shot.dialogue and not shot.character_ids:
            issues.append("Dialogue present but no character assigned")

        # Rule 4: Pacing validation
        if shot.panel_count > 3 and brief.pacing_note == "fast":
            issues.append("Fast pacing with >3 panels may feel rushed")

        # Rule 5: Panel count for close-ups
        if shot.shot_type in ("close-up", "extreme-close-up") and shot.panel_count > 1:
            issues.append("Close-up shots typically work best as single panels")

        if issues:
            return {
                "approved": False,
                "issues": issues,
                "note": "; ".join(issues),
                "reason": "Quality check failed",
            }

        return {"approved": True, "issues": [], "note": "", "reason": "All checks passed"}

    def review_sequence(self, briefs: list) -> list[dict]:
        """Review a sequence of ShotBriefs for overall pacing and flow."""
        results: list[dict] = []

        for i, brief in enumerate(briefs):
            result = self.review_shot(brief)

            # Sequence-level checks
            if i > 0:
                prev = briefs[i-1]
                # Check for repetitive shot types
                if brief.shot.shot_type == prev.shot.shot_type and brief.shot.shot_type in ("close-up", "extreme-close-up"):
                    result["issues"].append("Two consecutive close-ups — may feel static")
                    result["approved"] = False

            results.append(result)

        return results

    @staticmethod
    def _build_rulebook() -> dict:
        return {
            "layout_map": {
                "full-page": {"wide", "panorama", "long"},
                "1x2": {"long", "medium", "wide"},
                "2x2": {"medium", "close-up"},
                "1x1": {"close-up", "extreme-close-up"},
            },
            "max_panels": 4,
            "min_description_length": 20,
        }

    def _check_layout(self, layout: str, shot_type: str) -> bool:
        """Validate that the layout is appropriate for the shot type."""
        allowed = self.rules["layout_map"].get(layout, set())
        return shot_type in allowed or not allowed
