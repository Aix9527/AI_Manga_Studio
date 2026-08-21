"""Director Agent — top-level orchestrator for manga production decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import uuid4

from backend.story.models import Shot
from backend.agents.critic import CriticAgent


@dataclass
class ProductionDecision:
    """A single production decision made by the Director."""
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    shot_id: str = ""
    decision_type: str = ""    # panel_layout, angle_override, emphasis, pacing, cut, skip
    value: str = ""
    reason: str = ""
    confidence: float = 0.5
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ShotBrief:
    """Director's production brief for a single shot."""
    shot: Shot
    decisions: list[ProductionDecision] = field(default_factory=list)
    panel_layout: str = ""      # e.g. "2x2", "1x3", "full-page"
    emphasis: str = ""          # what to emphasize in this shot
    pacing_note: str = ""       # fast, slow, lingering
    mood_adjustment: str = ""   # mood override if needed
    approved: bool = False


class DirectorAgent:
    """
    Director Agent — makes high-level production decisions for manga adaptation.

    Responsibilities:
    - Decides panel layout per shot
    - Overrides camera angles when needed
    - Controls pacing rhythm
    - Coordinates Writer → Character → Critic pipeline
    """

    def __init__(self):
        self.writer = None       # WriterAgent (lazy init to avoid circular)
        self.character_agent = None
        self.critic = CriticAgent()
        self.briefs: dict[str, list[ShotBrief]] = {}  # novel_id → briefs

    def set_pipeline(self, writer, character_agent):
        """Wire up the agent pipeline."""
        self.writer = writer
        self.character_agent = character_agent

    def plan_shot(self, shot: Shot, scene_context: dict = None) -> ShotBrief:
        """
        Generate a production brief for a single shot.

        Director decides: panel layout, emphasis, pacing, angle overrides.
        """
        decisions: list[ProductionDecision] = []

        # Panel layout decision
        layout = self._decide_layout(shot)
        decisions.append(ProductionDecision(
            shot_id=shot.id, decision_type="panel_layout", value=layout,
            reason=f"Shot type '{shot.shot_type}' with {shot.panel_count} panel(s)",
        ))

        # Camera angle decision
        angle = self._decide_angle(shot)
        if angle != shot.camera_angle:
            decisions.append(ProductionDecision(
                shot_id=shot.id, decision_type="angle_override", value=angle,
                reason="Director override for visual impact",
            ))

        # Pacing decision
        pacing = self._decide_pacing(shot)
        decisions.append(ProductionDecision(
            shot_id=shot.id, decision_type="pacing", value=pacing,
            reason=f"Mood: {shot.emotion}, dialogue: {'yes' if shot.dialogue else 'no'}",
        ))

        # Emphasis decision
        emphasis = self._decide_emphasis(shot)
        decisions.append(ProductionDecision(
            shot_id=shot.id, decision_type="emphasis", value=emphasis,
            reason="Key visual focus point",
        ))

        brief = ShotBrief(
            shot=shot,
            decisions=decisions,
            panel_layout=layout,
            emphasis=emphasis,
            pacing_note=pacing,
            mood_adjustment=shot.emotion,
        )

        return brief

    def plan_sequence(self, shots: list[Shot]) -> list[ShotBrief]:
        """Plan production for a sequence of shots with pacing rhythm."""
        briefs: list[ShotBrief] = []

        for i, shot in enumerate(shots):
            brief = self.plan_shot(shot)

            # Pacing rhythm: vary panel sizes for visual interest
            if i > 0 and briefs[i-1].panel_layout == "full-page":
                brief.panel_layout = "1x2"

            # Inject character context
            if self.character_agent and shot.character_ids:
                for cid in shot.character_ids:
                    brief.decisions.append(ProductionDecision(
                        shot_id=shot.id,
                        decision_type="character_context",
                        value=cid,
                        reason="Character appearing in shot",
                    ))

            briefs.append(brief)

        return briefs

    def run_critique(self, briefs: list[ShotBrief]) -> list[ShotBrief]:
        """Run the Critic agent on a set of briefs, mark approved/rejected."""
        for brief in briefs:
            feedback = self.critic.review_shot(brief)
            brief.approved = feedback.get("approved", False)
            if not brief.approved:
                brief.decisions.append(ProductionDecision(
                    shot_id=brief.shot.id,
                    decision_type="revision_note",
                    value=feedback.get("note", ""),
                    reason=feedback.get("reason", ""),
                ))
        return briefs

    # ── Decision helpers ──

    @staticmethod
    def _decide_layout(shot: Shot) -> str:
        layouts = {
            "wide": "full-page",
            "panorama": "full-page",
            "long": "1x2",
            "medium": "2x2",
            "close-up": "1x1",
            "extreme-close-up": "1x1",
        }
        return layouts.get(shot.shot_type, "2x2")

    @staticmethod
    def _decide_angle(shot: Shot) -> str:
        if shot.emotion == "tense" and shot.camera_angle == "eye-level":
            return "dutch"
        return shot.camera_angle

    @staticmethod
    def _decide_pacing(shot: Shot) -> str:
        if shot.dialogue:
            return "slow"
        if shot.emotion in ("tense", "dramatic"):
            return "fast"
        if shot.shot_type in ("close-up", "extreme-close-up"):
            return "lingering"
        return "normal"

    @staticmethod
    def _decide_emphasis(shot: Shot) -> str:
        if shot.dialogue:
            return "dialogue bubble"
        if shot.character_ids:
            return f"character expression ({shot.character_ids[0]})"
        return "environment"
