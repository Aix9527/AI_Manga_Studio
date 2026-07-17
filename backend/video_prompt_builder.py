"""
AI Manga Studio V3.5 — Video Prompt Builder

Constructs structured Wan I2V video prompts.
Source: wan工作室爆量(2).txt

Key rules:
- Character names simplified to generic terms: 男人/女人/小孩/老人
- Motion trajectories must be concise
- 0-0.15s waste frames
- 动漫风格，逼真精细
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────

DISCARD_FRAME_NOTE: str = "0秒-0.15秒为固定废帧"

CHARACTER_SIMPLIFY_MAP: Dict[str, str] = {
    # Default mapping: character type → simplified term
    "male": "男人",
    "female": "女人",
    "child": "小孩",
    "elderly": "老人",
    "teen": "少年",
    "girl": "少女",
    "old_man": "老人",
    "old_woman": "老妇",
}


# ── Data Models ───────────────────────────────────────────────

@dataclass
class VideoPrompt:
    """Structured Wan I2V video prompt."""
    shot_id: str = ""

    frame_start: str = ""            # Starting frame description (0-0.15s waste)
    action_sequence: str = ""        # Time-ordered action sequence
    character_id: str = ""           # Simplified character name
    motion_trajectory: str = ""      # Motion trajectory description
    dialogue_timing: str = ""        # Dialogue timestamps
    video_style: str = ""            # Video style tags
    full_prompt: str = ""            # Synthesized complete prompt


# ── Engine ────────────────────────────────────────────────────

class VideoPromptBuilder:
    """Builds Wan I2V video prompts from structured shot data.

    Follows the core rule: keep prompts concise, use generic
    character terms, and focus on motion trajectories.
    """

    DEFAULT_VIDEO_STYLE: str = "动漫风格，逼真精细，光影真实，色彩自然"

    def __init__(self) -> None:
        logger.info("VideoPromptBuilder initialized (V3.5)")

    # ── Public API ────────────────────────────────────────

    def build(
        self,
        shot_data: Dict[str, Any],
        motion_plan: Optional[Dict[str, Any]] = None,
        camera_plan: Optional[Dict[str, Any]] = None,
        dialogue: str = "",
    ) -> VideoPrompt:
        """Build a Wan I2V video prompt.

        Args:
            shot_data: Shot data with at minimum: shot_id, character_action, scene_desc.
            motion_plan: MotionPlan dict from MotionPlanner.
            camera_plan: CameraConfig dict from CameraPlanner.
            dialogue: Character dialogue for timing.

        Returns:
            VideoPrompt with structured fields.
        """
        prompt = VideoPrompt(shot_id=shot_data.get("shot_id", ""))

        # Starting frame (waste frame declaration)
        prompt.frame_start = DISCARD_FRAME_NOTE

        # Simplify character identity
        prompt.character_id = self._simplify_character(shot_data)

        # Build action sequence
        prompt.action_sequence = self._build_action_sequence(shot_data, motion_plan)

        # Build motion trajectory
        prompt.motion_trajectory = self._build_motion_trajectory(
            shot_data, motion_plan, camera_plan
        )

        # Dialogue timing
        if dialogue:
            prompt.dialogue_timing = self._format_dialogue_timing(dialogue)

        # Style
        prompt.video_style = self.DEFAULT_VIDEO_STYLE

        # Synthesize full prompt
        prompt.full_prompt = self._synthesize_full(prompt)

        logger.debug(
            f"VideoPromptBuilder: built prompt for shot {prompt.shot_id}, "
            f"length={len(prompt.full_prompt)}"
        )
        return prompt

    def build_batch(
        self,
        shots: List[Dict[str, Any]],
        motion_plans: Optional[List[Dict[str, Any]]] = None,
        camera_plans: Optional[List[Dict[str, Any]]] = None,
    ) -> List[VideoPrompt]:
        """Build video prompts for a batch of shots."""
        prompts: List[VideoPrompt] = []

        for i, shot in enumerate(shots):
            motion = motion_plans[i] if motion_plans and i < len(motion_plans) else None
            camera = camera_plans[i] if camera_plans and i < len(camera_plans) else None

            prompt = self.build(
                shot_data=shot,
                motion_plan=motion,
                camera_plan=camera,
                dialogue=shot.get("dialogue", ""),
            )
            prompts.append(prompt)

        logger.info(f"VideoPromptBuilder: built {len(prompts)} video prompts")
        return prompts

    # ── Internal builders ─────────────────────────────────

    def _simplify_character(self, shot_data: Dict[str, Any]) -> str:
        """Simplify character name to generic term.

        Rule from prompt: must use 男人/女人/小孩/老人 generic terms.
        """
        char_info = shot_data.get("character_info", {})
        gender = char_info.get("gender", "unknown")
        age = char_info.get("age", 30)

        if age < 14:
            return "小孩"
        if age > 60:
            return "老人"
        if gender == "male":
            return "男人"
        if gender == "female":
            return "女人"

        # Fallback: check character_action for clues
        action = shot_data.get("character_action", "")
        scene_desc = shot_data.get("scene_desc", "")

        if "少年" in action or "少年" in scene_desc:
            return "少年"
        if "少女" in action or "少女" in scene_desc:
            return "少女"

        return "角色"

    def _build_action_sequence(
        self,
        shot_data: Dict[str, Any],
        motion_plan: Optional[Dict[str, Any]],
    ) -> str:
        """Build time-ordered action sequence."""
        parts: List[str] = []

        # From shot data
        action = shot_data.get("character_action", "")
        if action:
            parts.append(action)

        # From motion plan
        if motion_plan:
            body = motion_plan.get("body_motion", "")
            face = motion_plan.get("facial_motion", "")
            hand = motion_plan.get("hand_action", "")

            if body and body != action:
                parts.append(body)
            if face:
                parts.append(face)
            if hand:
                parts.append(hand)

        return "。".join(parts[:3]) + "。" if parts else "角色保持静止。"

    def _build_motion_trajectory(
        self,
        shot_data: Dict[str, Any],
        motion_plan: Optional[Dict[str, Any]],
        camera_plan: Optional[Dict[str, Any]],
    ) -> str:
        """Build concise motion trajectory description."""
        char_id = self._simplify_character(shot_data)
        parts: List[str] = []

        # Camera motion from camera plan
        if camera_plan:
            cam_movement_cn = camera_plan.get("camera_movement", "")
            cam_movement_en = camera_plan.get("camera_movement_en", "")

            if cam_movement_cn:
                parts.append(f"镜头{cam_movement_cn}")

        # Character motion from motion plan
        if motion_plan:
            camera_micro = motion_plan.get("camera_micro_motion", "")
            if camera_micro:
                parts.append(camera_micro)

        if not parts:
            parts.append(f"{char_id}保持静止，镜头固定")

        return "。".join(parts) + "。"

    def _format_dialogue_timing(self, dialogue: str) -> str:
        """Format dialogue with timestamp."""
        if not dialogue:
            return ""

        char_count = len(dialogue)
        duration = max(1.5, char_count / 3.0)
        return f"对话时间戳: {dialogue} (约{duration:.1f}秒)"

    def _synthesize_full(self, prompt: VideoPrompt) -> str:
        """Combine all fields into a complete Wan I2V prompt."""
        lines: List[str] = []

        if prompt.frame_start:
            lines.append(prompt.frame_start)

        if prompt.action_sequence:
            lines.append(prompt.action_sequence)

        if prompt.motion_trajectory:
            lines.append(prompt.motion_trajectory)

        if prompt.dialogue_timing:
            lines.append(prompt.dialogue_timing)

        if prompt.video_style:
            lines.append(prompt.video_style)

        return "\n".join(lines)
