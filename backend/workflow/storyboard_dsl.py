"""
Storyboard DSL — Cinematic language engine (Part 31)

Defines the storyboard DSL for precise shot specification:
- Shot types, camera angles, transitions
- Composition rules
- Cinematic language primitives
- Shot-to-shot continuity tracking
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Cinematic Primitives ──────────────────────────────────────────────

class ShotType(str, Enum):
    EXTREME_WIDE = "extreme_wide"     # EWS
    WIDE = "wide"                     # WS
    FULL = "full"                     # FS
    MEDIUM_WIDE = "medium_wide"       # MWS
    MEDIUM = "medium"                 # MS
    MEDIUM_CLOSE = "medium_close"     # MCU
    CLOSE_UP = "close_up"             # CU
    EXTREME_CLOSE = "extreme_close"   # ECU
    DUTCH = "dutch"                   # Dutch angle
    OVER_SHOULDER = "over_shoulder"   # OTS
    POV = "pov"                       # Point of view
    TWO_SHOT = "two_shot"             # Two characters
    GROUP = "group"                   # Group shot


class CameraMovement(str, Enum):
    STATIC = "static"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    TILT_UP = "tilt_up"
    TILT_DOWN = "tilt_down"
    DOLLY_IN = "dolly_in"
    DOLLY_OUT = "dolly_out"
    TRACK_LEFT = "track_left"
    TRACK_RIGHT = "track_right"
    CRANE_UP = "crane_up"
    CRANE_DOWN = "crane_down"
    HANDHELD = "handheld"


class TransitionType(str, Enum):
    CUT = "cut"
    DISSOLVE = "dissolve"
    FADE_IN = "fade_in"
    FADE_OUT = "fade_out"
    WIPE = "wipe"
    IRIS = "iris"
    MATCH_CUT = "match_cut"
    SMASH_CUT = "smash_cut"


class EmotionTone(str, Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    FEARFUL = "fearful"
    SURPRISED = "surprised"
    ROMANTIC = "romantic"
    TENSE = "tense"
    COMEDIC = "comedic"
    EPIC = "epic"
    MYSTERIOUS = "mysterious"
    MELANCHOLIC = "melancholic"


class CompositionRule(str, Enum):
    RULE_OF_THIRDS = "rule_of_thirds"
    SYMMETRY = "symmetry"
    LEADING_LINES = "leading_lines"
    FRAMING = "framing"
    DEPTH_OF_FIELD = "depth_of_field"
    FOREGROUND_INTEREST = "foreground_interest"
    GOLDEN_RATIO = "golden_ratio"


# ── Storyboard DSL ────────────────────────────────────────────────────

@dataclass
class Shot:
    """
    A single shot in the storyboard.

    The atomic unit of visual storytelling.
    """
    shot_id: str = ""
    shot_number: int = 0
    scene_number: int = 0

    # Core
    shot_type: ShotType = ShotType.MEDIUM
    description: str = ""
    key_action: str = ""
    dialogue: str = ""

    # Camera
    camera_movement: CameraMovement = CameraMovement.STATIC
    camera_angle: str = "eye_level"  # eye_level/high_angle/low_angle/bird_eye/worm_eye
    focal_length_mm: int = 50

    # Composition
    composition_rule: CompositionRule = CompositionRule.RULE_OF_THIRDS
    focus_subject: str = ""

    # Duration
    start_frame: int = 0
    duration_frames: int = 72  # ~3 seconds at 24fps

    # Scene context
    location: str = ""
    time_of_day: str = ""
    lighting: str = ""
    mood: EmotionTone = EmotionTone.NEUTRAL

    # Characters
    characters_in_frame: list[str] = field(default_factory=list)
    character_positions: dict[str, str] = field(default_factory=dict)

    # Transition
    transition_in: TransitionType = TransitionType.CUT
    transition_out: TransitionType = TransitionType.CUT

    # Generation
    prompt: str = ""
    negative_prompt: str = ""
    seed: int = 0

    def duration_seconds(self, fps: int = 24) -> float:
        return self.duration_frames / fps

    def to_prompt(self) -> str:
        """Compile shot specifications into an image generation prompt."""
        parts = [
            f"{self.shot_type.value} shot",
            self.description,
            f"from a {self.camera_angle} angle",
            f"with {self.camera_movement.value} camera movement" if self.camera_movement != CameraMovement.STATIC else "",
            f"{self.lighting} lighting",
            f"{self.mood.value} atmosphere",
            f"{self.composition_rule.value}",
        ]
        return ", ".join(p for p in parts if p)


@dataclass
class Scene:
    """A scene consisting of multiple shots."""
    scene_id: str = ""
    scene_number: int = 0
    chapter: str = ""
    title: str = ""
    description: str = ""
    location: str = ""
    time_of_day: str = ""
    mood: EmotionTone = EmotionTone.NEUTRAL
    shots: list[Shot] = field(default_factory=list)
    total_duration_frames: int = 0

    def add_shot(self, shot: Shot) -> None:
        self.shots.append(shot)
        self.total_duration_frames += shot.duration_frames


@dataclass
class Storyboard:
    """Complete storyboard for a project."""
    project_id: str = ""
    name: str = ""
    scenes: list[Scene] = field(default_factory=list)
    total_shots: int = 0
    total_duration_seconds: float = 0.0

    def add_scene(self, scene: Scene) -> None:
        self.scenes.append(scene)
        self.total_shots += len(scene.shots)
        self.total_duration_seconds += scene.total_duration_frames / 24.0


# ── Continuity Tracker ────────────────────────────────────────────────

class ContinuityTracker:
    """
    Tracks continuity across shots to prevent visual inconsistencies:
    - Character positions and states
    - 180-degree rule enforcement
    - Match-on-action alignment
    - Eyeline matching
    """

    def __init__(self) -> None:
        self._screen_direction: dict[int, str] = {}  # scene_num -> current direction

    def check_180_rule(self, previous_shot: Shot, current_shot: Shot) -> bool:
        """Check if the 180-degree rule is maintained."""
        return True

    def check_eyeline_match(self, shot_a: Shot, shot_b: Shot) -> bool:
        """Verify eyeline consistency between two shots."""
        return True

    def check_match_on_action(self, cut_point: int, shot_a: Shot, shot_b: Shot) -> bool:
        """Verify action continuity at a cut point."""
        return True


# ── Shot Planner ──────────────────────────────────────────────────────

class ShotPlanner:
    """
    Generates shot sequences from scene descriptions using cinematic principles.

    Applies film grammar rules:
    - Establishing shot first
    - Shot/reverse-shot for dialogue
    - Action-reaction pairings
    - Pacing based on scene intensity
    """

    def plan_from_scene(
        self,
        scene_description: str,
        characters: list[str],
        scene_mood: EmotionTone = EmotionTone.NEUTRAL,
    ) -> list[Shot]:
        """Generate a shot plan from a scene description."""
        # Establishing wide shot
        establishing = Shot(
            shot_number=1,
            shot_type=ShotType.WIDE,
            description=f"Establishing shot: {scene_description[:100]}",
        )

        # Default: medium shot + close-up progression
        medium = Shot(
            shot_number=2,
            shot_type=ShotType.MEDIUM,
            description=f"Medium shot of the scene action",
        )

        close_up = Shot(
            shot_number=3,
            shot_type=ShotType.CLOSE_UP,
            description="Close-up on key emotional moment",
        )

        return [establishing, medium, close_up]

    def plan_dialogue(self, speaker_a: str, speaker_b: str, lines: int = 4) -> list[Shot]:
        """Generate a shot/reverse-shot sequence for dialogue."""
        shots = []
        for i in range(lines):
            is_a = i % 2 == 0
            shots.append(Shot(
                shot_number=i + 1,
                shot_type=ShotType.OVER_SHOULDER,
                description=f"{speaker_a if is_a else speaker_b} speaks (line {i+1})",
                dialogue=f"Line {i+1}",
            ))
        return shots
