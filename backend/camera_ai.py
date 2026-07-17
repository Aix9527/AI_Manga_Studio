"""
AI Manga Studio Pro V1.0 — Camera AI

Intelligent camera direction module that automatically decides
camera angles, shot types, lens choices, and camera movements
based on scene content, emotional tone, and narrative pacing.

Camera AI analyzes each shot context and outputs a structured
camera directive including:
- Shot type (CloseUp, Medium, Wide, etc.)
- Camera angle (Eye Level, Low Angle, High Angle, Dutch Angle)
- Lens choice (24mm, 50mm, 85mm, 135mm)
- Movement (Static, Pan, Tilt, Dolly, Tracking, Crane)
- Depth of field (Shallow, Medium, Deep)
- Composition rule (Rule of Thirds, Center, Leading Lines)
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from loguru import logger

from backend.models import ShotType


# ============================================================
# Enums
# ============================================================

class CameraAngle(str, Enum):
    eye_level = "EyeLevel"
    low_angle = "LowAngle"
    high_angle = "HighAngle"
    dutch_angle = "DutchAngle"
    birds_eye = "BirdsEye"
    worms_eye = "WormsEye"
    over_shoulder = "OverShoulder"


class LensType(str, Enum):
    wide_24 = "24mm"
    standard_50 = "50mm"
    portrait_85 = "85mm"
    tele_135 = "135mm"
    macro = "Macro"


class CameraMovement(str, Enum):
    static = "Static"
    pan_left = "PanLeft"
    pan_right = "PanRight"
    tilt_up = "TiltUp"
    tilt_down = "TiltDown"
    dolly_in = "DollyIn"
    dolly_out = "DollyOut"
    tracking = "Tracking"
    crane_up = "CraneUp"
    crane_down = "CraneDown"
    handheld = "Handheld"


class DepthOfField(str, Enum):
    shallow = "Shallow"
    medium = "Medium"
    deep = "Deep"


class CompositionRule(str, Enum):
    rule_of_thirds = "RuleOfThirds"
    center = "Center"
    leading_lines = "LeadingLines"
    symmetry = "Symmetry"
    frame_within_frame = "FrameWithinFrame"
    golden_ratio = "GoldenRatio"


# ============================================================
# Data Classes
# ============================================================

@dataclass
class CameraDirective:
    """Complete camera directive for a shot."""
    shot_index: int
    shot_type: ShotType = ShotType.medium
    angle: CameraAngle = CameraAngle.eye_level
    lens: LensType = LensType.standard_50
    movement: CameraMovement = CameraMovement.static
    depth_of_field: DepthOfField = DepthOfField.medium
    composition: CompositionRule = CompositionRule.rule_of_thirds
    focal_point: str = "center"
    description: str = ""


# ============================================================
# Camera AI Engine
# ============================================================

class CameraAI:
    """Analyzes narrative context and outputs optimal camera directives.

    Uses rule-based heuristics to decide camera settings based on:
    - Emotional intensity → shot type & angle
    - Action dynamics → movement
    - Character count → composition & framing
    - Scene scale → lens choice
    - Narrative pacing → movement complexity
    """

    # Emotion → shot type mapping
    EMOTION_SHOT_TYPE: dict = {
        "neutral": ShotType.medium,
        "happy": ShotType.medium,
        "sad": ShotType.close_up,
        "angry": ShotType.close_up,
        "surprised": ShotType.close_up,
        "fearful": ShotType.close_up,
        "sorrowful": ShotType.close_up,
        "joyful": ShotType.medium,
        "worried": ShotType.close_up,
        "loving": ShotType.close_up,
        "hateful": ShotType.close_up,
        "confused": ShotType.close_up,
        "determined": ShotType.medium,
        "trembling": ShotType.close_up,
        "sighing": ShotType.medium,
    }

    # Emotion → angle mapping
    EMOTION_ANGLE: dict = {
        "neutral": CameraAngle.eye_level,
        "happy": CameraAngle.eye_level,
        "sad": CameraAngle.high_angle,
        "angry": CameraAngle.low_angle,
        "surprised": CameraAngle.eye_level,
        "fearful": CameraAngle.high_angle,
        "sorrowful": CameraAngle.high_angle,
        "joyful": CameraAngle.low_angle,
        "worried": CameraAngle.eye_level,
        "loving": CameraAngle.eye_level,
        "hateful": CameraAngle.low_angle,
        "confused": CameraAngle.dutch_angle,
        "determined": CameraAngle.low_angle,
    }

    # Character count → shot type
    CHARACTER_COUNT_SHOT: dict = {
        0: ShotType.wide,       # no characters → establishing shot
        1: ShotType.medium,     # single character → medium
        2: ShotType.two_shot,   # two characters → two-shot framing
    }

    # Action intensity → movement
    ACTION_MOVEMENT: dict = {
        "静止": CameraMovement.static,
        "走": CameraMovement.tracking,
        "跑": CameraMovement.tracking,
        "追": CameraMovement.tracking,
        "飞": CameraMovement.crane_up,
        "跳": CameraMovement.crane_up,
        "冲": CameraMovement.tracking,
        "奔": CameraMovement.tracking,
        "转身": CameraMovement.pan_left,
        "回头": CameraMovement.pan_left,
        "抬头": CameraMovement.tilt_up,
        "低头": CameraMovement.tilt_down,
        "坠落": CameraMovement.crane_down,
        "攀爬": CameraMovement.tilt_up,
    }

    def __init__(self) -> None:
        """Initialize Camera AI with default settings."""
        self.pacing: str = "normal"  # slow / normal / fast / action
        self.preferred_lens: Optional[LensType] = None
        self.shake_intensity: float = 0.0

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def set_pacing(self, pacing: str) -> None:
        """Set narrative pacing to influence camera decisions.

        Args:
            pacing: 'slow', 'normal', 'fast', or 'action'.
        """
        valid = {"slow", "normal", "fast", "action"}
        if pacing in valid:
            self.pacing = pacing
            logger.info(f"CameraAI: Pacing set to '{pacing}'")
        else:
            logger.warning(f"CameraAI: Invalid pacing '{pacing}'")

    def decide_camera(
        self,
        shot_index: int,
        shot_type: Optional[ShotType] = None,
        emotion: str = "neutral",
        action: str = "",
        character_count: int = 1,
        scene_scale: str = "indoor",
        dialogue_present: bool = False,
        is_action_peak: bool = False,
        is_establishing: bool = False,
    ) -> CameraDirective:
        """Decide the optimal camera settings for a shot.

        Args:
            shot_index: Shot index within the chapter.
            shot_type: Pre-specified shot type (from AI Director), or None.
            emotion: Emotional state keyword.
            action: Action description.
            character_count: Number of characters in the shot.
            scene_scale: 'indoor', 'outdoor', or 'epic'.
            dialogue_present: Whether dialogue is spoken in this shot.
            is_action_peak: Whether this is an action climax moment.
            is_establishing: Whether this is an establishing shot.

        Returns:
            CameraDirective with all settings.
        """
        # 1. Shot type
        if shot_type:
            final_shot_type = shot_type
        elif is_establishing:
            final_shot_type = ShotType.wide
        elif character_count in self.CHARACTER_COUNT_SHOT:
            final_shot_type = self.CHARACTER_COUNT_SHOT[character_count]
        else:
            final_shot_type = self.EMOTION_SHOT_TYPE.get(
                emotion, ShotType.medium
            )

        # Override for 3+ characters
        if character_count >= 3:
            final_shot_type = ShotType.wide

        # 2. Camera angle
        angle = self.EMOTION_ANGLE.get(emotion, CameraAngle.eye_level)
        if is_action_peak:
            angle = CameraAngle.low_angle  # hero angle
        if is_establishing:
            angle = CameraAngle.birds_eye

        # 3. Lens
        lens = self._decide_lens(final_shot_type, scene_scale, dialogue_present)

        # 4. Movement
        movement = self._decide_movement(
            action=action,
            dialogue_present=dialogue_present,
            is_action_peak=is_action_peak,
            is_establishing=is_establishing,
        )

        # 5. Depth of field
        dof = self._decide_depth_of_field(final_shot_type)

        # 6. Composition
        composition = self._decide_composition(
            character_count=character_count,
            is_establishing=is_establishing,
            dialogue_present=dialogue_present,
        )

        # 7. Build description
        description = self._build_description(
            shot_type=final_shot_type,
            angle=angle,
            lens=lens,
            movement=movement,
            dof=dof,
            composition=composition,
        )

        return CameraDirective(
            shot_index=shot_index,
            shot_type=final_shot_type,
            angle=angle,
            lens=lens,
            movement=movement,
            depth_of_field=dof,
            composition=composition,
            description=description,
        )

    def decide_sequence(
        self,
        shot_data: List[dict],
    ) -> List[CameraDirective]:
        """Decide camera settings for a sequence of shots.

        Ensures variety across consecutive shots to avoid monotony.

        Args:
            shot_data: List of dicts with keys matching decide_camera params.

        Returns:
            List of CameraDirective objects.
        """
        directives: List[CameraDirective] = []
        last_shot_type: Optional[ShotType] = None

        for i, data in enumerate(shot_data):
            # Avoid repeating the same shot type 3+ times
            shot_type = data.get("shot_type")
            if (
                shot_type
                and last_shot_type
                and shot_type == last_shot_type
                and i >= 2
                and directives[-1].shot_type == shot_type
            ):
                # Cycle to next shot type
                alternatives = [
                    ShotType.medium,
                    ShotType.close_up,
                    ShotType.wide,
                ]
                try:
                    idx = alternatives.index(shot_type)
                    shot_type = alternatives[(idx + 1) % len(alternatives)]
                except ValueError:
                    pass

            directive = self.decide_camera(
                shot_index=data.get("index", i),
                shot_type=shot_type,
                emotion=data.get("emotion", "neutral"),
                action=data.get("action", ""),
                character_count=data.get("character_count", 1),
                scene_scale=data.get("scene_scale", "indoor"),
                dialogue_present=data.get("dialogue", "") != "",
                is_action_peak=data.get("is_action_peak", False),
                is_establishing=data.get("is_establishing", False),
            )
            directives.append(directive)
            last_shot_type = directive.shot_type

        logger.info(f"CameraAI: Decided sequence of {len(directives)} shots")
        return directives

    # ----------------------------------------------------------
    # Internal Decision Logic
    # ----------------------------------------------------------

    def _decide_lens(
        self,
        shot_type: ShotType,
        scene_scale: str,
        dialogue_present: bool,
    ) -> LensType:
        """Decide lens based on shot type and scene scale.

        Args:
            shot_type: Current shot type.
            scene_scale: Scene scale.
            dialogue_present: Whether dialogue exists.

        Returns:
            Selected LensType.
        """
        if self.preferred_lens:
            return self.preferred_lens

        if shot_type == ShotType.close_up:
            return LensType.portrait_85
        elif shot_type in (ShotType.wide, ShotType.drone):
            return LensType.wide_24 if scene_scale == "epic" else LensType.standard_50
        elif shot_type == ShotType.tracking:
            return LensType.standard_50
        else:
            return LensType.portrait_85 if dialogue_present else LensType.standard_50

    def _decide_movement(
        self,
        action: str,
        dialogue_present: bool,
        is_action_peak: bool,
        is_establishing: bool,
    ) -> CameraMovement:
        """Decide camera movement.

        Args:
            action: Action description.
            dialogue_present: Whether dialogue exists.
            is_action_peak: Whether this is action climax.
            is_establishing: Whether this is establishing shot.

        Returns:
            Selected CameraMovement.
        """
        # Pacing override
        if self.pacing == "action":
            return CameraMovement.handheld

        # Action-driven movement
        if action:
            for action_word, move in self.ACTION_MOVEMENT.items():
                if action_word in action:
                    return move

        # Dialogue → static
        if dialogue_present:
            return CameraMovement.static

        # Establishing shot → crane
        if is_establishing:
            return CameraMovement.crane_up

        # Action peak → handheld
        if is_action_peak:
            return CameraMovement.handheld

        # Default: static with occasional subtle pan
        return CameraMovement.static

    def _decide_depth_of_field(self, shot_type: ShotType) -> DepthOfField:
        """Decide depth of field.

        Args:
            shot_type: Current shot type.

        Returns:
            Selected DepthOfField.
        """
        if shot_type == ShotType.close_up:
            return DepthOfField.shallow
        elif shot_type == ShotType.wide:
            return DepthOfField.deep
        else:
            return DepthOfField.medium

    def _decide_composition(
        self,
        character_count: int,
        is_establishing: bool,
        dialogue_present: bool,
    ) -> CompositionRule:
        """Decide composition rule.

        Args:
            character_count: Number of characters.
            is_establishing: Whether establishing.
            dialogue_present: Whether dialogue exists.

        Returns:
            Selected CompositionRule.
        """
        if is_establishing:
            return CompositionRule.leading_lines
        if character_count == 0:
            return CompositionRule.symmetry
        if character_count == 1:
            return CompositionRule.rule_of_thirds
        if character_count == 2 and dialogue_present:
            return CompositionRule.rule_of_thirds
        return CompositionRule.center

    def _build_description(
        self,
        shot_type: ShotType,
        angle: CameraAngle,
        lens: LensType,
        movement: CameraMovement,
        dof: DepthOfField,
        composition: CompositionRule,
    ) -> str:
        """Build a human-readable camera description.

        Args:
            shot_type: Shot type.
            angle: Camera angle.
            lens: Lens type.
            movement: Camera movement.
            dof: Depth of field.
            composition: Composition rule.

        Returns:
            Description string.
        """
        parts = [
            f"{shot_type.value} shot",
            f"{angle.value} angle",
            f"{lens.value} lens",
            f"{movement.value} movement",
            f"{dof.value} depth of field",
            f"{composition.value} composition",
        ]
        return ", ".join(parts)
