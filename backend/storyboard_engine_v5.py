"""
AI Manga Studio Pro V5 — Storyboard Engine Upgrade

Upgraded storyboard engine with:
- Cinematic lighting design per shot
- Shot type selection (close/medium/wide/drone/pov/tracking/dutch/overhead)
- Camera movement planning
- Transition design (cut/fade/dissolve/whip/match)
- Emotion-aware shot composition
- Scene-to-shot mapping
- Professional storyboarding output (JSON + visual layout hints)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.director_video_prompt_builder import CinematicShot


# ============================================================
# Constants
# ============================================================

# Shot type recommendations based on narrative function
SHOT_TYPE_RECOMMENDATIONS = {
    "establishing": "wide",           # 建立镜头用远景
    "dialogue": "medium",             # 对话用中景
    "reaction": "close",              # 反应镜头用特写
    "action": "tracking",             # 动作用跟拍
    "emotion": "extreme_close",       # 情绪用极特写
    "transition": "wide",             # 转场用远景
    "intimate": "close",              # 亲密场景用近景
    "epic": "drone",                  # 史诗场景用航拍
    "tension": "dutch",               # 紧张用荷兰角
    "immersive": "pov",               # 沉浸用主观视角
    "relationship": "two_shot",       # 关系用双人镜头
    "reveal": "over_shoulder",        # 揭示用过肩镜头
}

# Transition types and their use cases
TRANSITION_TYPES = {
    "cut": "标准硬切，最常用",
    "fade": "淡入淡出，时间流逝或情绪转换",
    "dissolve": "叠化，柔和过渡，记忆/梦境",
    "whip": "甩镜头，快速转向，制造冲击力",
    "match": "匹配剪辑，形状/动作相似性连接",
    "wipe": "擦除转场，风格化过渡",
    "zoom": "缩放转场，快速推进/拉出",
}

# Camera movement by scene mood
MOOD_CAMERA_MAP = {
    "tense": ["handheld", "slow_zoom", "dutch"],
    "romantic": ["slow_push_in", "orbit", "steadicam"],
    "action": ["whip_pan", "handheld_shake", "tracking"],
    "sad": ["crane_up", "pull_out", "static"],
    "happy": ["push_in", "tilt_up", "steadicam"],
    "mysterious": ["slow_zoom", "rack_focus", "static"],
    "epic": ["crane_up", "orbit", "drone"],
    "intimate": ["dolly_in", "close", "static"],
    "chaotic": ["handheld_shake", "whip_pan", "tracking"],
    "calm": ["steadicam", "slow_pan", "static"],
}


# ============================================================
# Data Models
# ============================================================

@dataclass
class StoryboardPanel:
    """A single storyboard panel (分镜画面)."""
    shot_number: int = 0
    shot_type: str = "medium"
    camera_angle: str = "eye_level"
    camera_movement: str = ""
    description: str = ""
    dialogue: str = ""
    lighting: str = ""
    vfx: str = ""
    duration: float = 5.0
    transition_in: str = "cut"
    transition_out: str = "cut"
    emotion: str = "neutral"
    characters: List[str] = field(default_factory=list)
    notes: str = ""
    visual_layout: str = ""  # e.g., "rule_of_thirds", "centered", "left_weighted"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_number": self.shot_number,
            "shot_type": self.shot_type,
            "camera_angle": self.camera_angle,
            "camera_movement": self.camera_movement,
            "description": self.description,
            "dialogue": self.dialogue,
            "lighting": self.lighting,
            "vfx": self.vfx,
            "duration": self.duration,
            "transition_in": self.transition_in,
            "transition_out": self.transition_out,
            "emotion": self.emotion,
            "characters": self.characters,
            "notes": self.notes,
            "visual_layout": self.visual_layout,
        }


# ============================================================
# Storyboard Engine
# ============================================================

class StoryboardEngine:
    """Cinematic storyboard engine for manga/video production.

    Generates structured storyboard panels from shot data,
    with professional cinematography guidance.
    """

    def __init__(self):
        logger.info("StoryboardEngine initialized (V5)")

    def generate_storyboard(
        self,
        shots: List[Dict[str, Any]],
        scene_context: Optional[Dict[str, Any]] = None,
    ) -> List[StoryboardPanel]:
        """Generate storyboard panels from shot data.

        Args:
            shots: List of shot dicts with keys like:
                - text/narration: the scene description
                - emotion: emotional tone
                - characters: list of character names
                - dialogue: spoken lines
                - action: character actions
                - scene: scene name/description
            scene_context: Optional scene metadata (time, weather, mood).

        Returns:
            List of StoryboardPanel objects.
        """
        panels = []

        # Default scene context
        if not scene_context:
            scene_context = {
                "time_of_day": "day",
                "weather": "clear",
                "mood": "neutral",
            }

        for i, shot_data in enumerate(shots):
            panel = self._build_panel(shot_data, scene_context, i + 1)
            panels.append(panel)

        logger.info(f"StoryboardEngine: generated {len(panels)} storyboard panels")
        return panels

    def generate_from_cinematic_shots(
        self,
        cinematic_shots: List[CinematicShot],
    ) -> List[StoryboardPanel]:
        """Generate storyboard panels from CinematicShot objects."""
        panels = []
        for i, cs in enumerate(cinematic_shots):
            panel = StoryboardPanel(
                shot_number=cs.shot_num,
                shot_type=cs.shot_type,
                camera_angle=self._infer_angle(cs),
                camera_movement=cs.camera_movement,
                description=self._describe_shot(cs),
                dialogue=cs.dialogue,
                lighting=self._describe_lighting(cs),
                vfx=", ".join(cs.visual_effects) if cs.visual_effects else "",
                duration=cs.duration_sec,
                transition_in=cs.transition_in,
                transition_out=cs.transition_out,
                emotion=cs.emotion,
                characters=cs.characters,
                notes=self._build_notes(cs),
                visual_layout=self._suggest_layout(cs),
            )
            panels.append(panel)
        return panels

    def export_json(self, panels: List[StoryboardPanel], filepath: str) -> None:
        """Export storyboard panels to JSON file."""
        data = {
            "panels": [p.to_dict() for p in panels],
            "metadata": {
                "total_panels": len(panels),
                "total_duration": sum(p.duration for p in panels),
                "exported_at": self._timestamp(),
            },
        }
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"StoryboardEngine: exported to {filepath}")

    # ---- Internal Methods ----

    def _build_panel(
        self,
        shot_data: Dict[str, Any],
        scene_context: Dict[str, Any],
        index: int,
    ) -> StoryboardPanel:
        """Build a single storyboard panel from shot data."""
        emotion = shot_data.get("emotion", "neutral")
        action = shot_data.get("action", "")
        characters = shot_data.get("characters", [])
        dialogue = shot_data.get("dialogue", "")

        # Recommend shot type
        shot_type = self._recommend_shot_type(emotion, action, characters)

        # Recommend camera movement
        camera_movement = self._recommend_camera_movement(emotion, action)

        # Recommend transition
        transition_in = shot_data.get("transition_in", "cut")
        transition_out = shot_data.get("transition_out", "cut")

        # Lighting
        lighting = self._recommend_lighting(scene_context, emotion)

        # Duration
        duration = shot_data.get("duration", 5.0)
        if not duration:
            duration = self._estimate_duration(action, dialogue)

        return StoryboardPanel(
            shot_number=index,
            shot_type=shot_type,
            camera_angle=self._infer_angle_from_type(shot_type),
            camera_movement=camera_movement,
            description=shot_data.get("text", shot_data.get("narration", "")),
            dialogue=dialogue,
            lighting=lighting,
            duration=duration,
            transition_in=transition_in,
            transition_out=transition_out,
            emotion=emotion,
            characters=characters,
            notes=shot_data.get("notes", ""),
            visual_layout=self._suggest_layout_from_type(shot_type),
        )

    def _recommend_shot_type(
        self,
        emotion: str,
        action: str,
        characters: List[str],
    ) -> str:
        """Recommend shot type based on narrative context."""
        # Check for action keywords
        action_keywords = ["fight", "attack", "run", "jump", "cast_spell"]
        if any(kw in action.lower() for kw in action_keywords):
            return "tracking"

        # Check for emotional intensity
        intense_emotions = ["angry", "fearful", "surprised", "excited"]
        if emotion in intense_emotions:
            return "close"

        # Multiple characters
        if len(characters) >= 2:
            return "two_shot"

        # Default
        return "medium"

    def _recommend_camera_movement(
        self,
        emotion: str,
        action: str,
    ) -> str:
        """Recommend camera movement based on mood."""
        # Action gets dynamic movement
        if any(kw in action.lower() for kw in ["fight", "attack", "run"]):
            return "handheld"

        # Emotional moments get slow movement
        emotional = ["sad", "happy", "tense", "determined"]
        if emotion in emotional:
            return "slow_push_in"

        return "static"

    def _recommend_lighting(
        self,
        scene_context: Dict[str, Any],
        emotion: str,
    ) -> str:
        """Recommend lighting based on scene and emotion."""
        time_of_day = scene_context.get("time_of_day", "day")
        weather = scene_context.get("weather", "clear")

        # Weather overrides
        if weather in ("rain", "storm", "snow"):
            return f"{weather} lighting, atmospheric particles"

        # Time of day
        lighting_map = {
            "dawn": "soft dawn light, pink-orange gradient, volumetric rays",
            "morning": "bright morning light, crisp shadows",
            "noon": "harsh overhead light, high contrast",
            "afternoon": "golden hour light, warm tones, long shadows",
            "dusk": "dusk cinematic light, orange horizon, blue fill",
            "night": "moonlight blue wash, warm practical accents",
        }

        base = lighting_map.get(time_of_day, lighting_map["morning"])

        # Emotion overlay
        emotion_lighting = {
            "angry": "high contrast, harsh shadows",
            "sad": "soft diffused, desaturated",
            "happy": "warm golden, bright",
            "fearful": "cold blue, deep shadows",
            "tense": "chiaroscuro, dramatic contrast",
        }
        if emotion in emotion_lighting:
            base += f", {emotion_lighting[emotion]}"

        return base

    def _estimate_duration(self, action: str, dialogue: str) -> float:
        """Estimate shot duration from content."""
        duration = 3.0  # default

        if dialogue:
            duration = max(duration, len(dialogue) / 3.0 + 1.0)

        if action:
            action_len = len(action)
            if action_len > 50:
                duration = max(duration, 5.0)
            elif action_len > 20:
                duration = max(duration, 3.5)

        return round(min(duration, 15.0), 1)

    def _infer_angle(self, cs: CinematicShot) -> str:
        """Infer camera angle from CinematicShot."""
        return cs.angle if hasattr(cs, "angle") else "eye_level"

    def _infer_angle_from_type(self, shot_type: str) -> str:
        """Infer angle from shot type."""
        angles = {
            "wide": "eye_level",
            "close": "eye_level",
            "medium": "eye_level",
            "drone": "high_angle",
            "pov": "eye_level",
            "tracking": "eye_level",
            "dutch": "dutch_tilt",
            "overhead": "top_down",
            "two_shot": "eye_level",
            "over_shoulder": "over_shoulder",
        }
        return angles.get(shot_type, "eye_level")

    def _describe_shot(self, cs: CinematicShot) -> str:
        """Generate a visual description of the shot."""
        parts = []

        if cs.characters:
            parts.append(f"Characters: {', '.join(cs.characters)}")

        if cs.character_actions:
            parts.append(f"Action: {'; '.join(cs.character_actions)}")

        if cs.scene_description:
            parts.append(f"Scene: {cs.scene_description}")

        return " | ".join(parts) if parts else "Standard shot composition"

    def _describe_lighting(self, cs: CinematicShot) -> str:
        """Describe lighting for the shot."""
        if cs.custom_lighting:
            return cs.custom_lighting

        tod = cs.time_of_day if hasattr(cs, "time_of_day") else "day"
        weather = cs.weather if hasattr(cs, "weather") else "clear"

        lighting_map = {
            "dawn": "soft dawn light",
            "morning": "bright morning light",
            "noon": "harsh overhead light",
            "afternoon": "golden hour light",
            "dusk": "dusk cinematic light",
            "night": "moonlight blue wash",
            "day": "bright daylight",
        }

        base = lighting_map.get(tod.lower(), lighting_map["day"])
        if weather != "clear":
            base += f", {weather} atmosphere"

        return base

    def _build_notes(self, cs: CinematicShot) -> str:
        """Build director notes for the shot."""
        notes = []

        if cs.emotion != "neutral":
            notes.append(f"Emotion: {cs.emotion}")

        if cs.transition_in != "cut":
            notes.append(f"Transition in: {cs.transition_in}")

        if cs.transition_out != "cut":
            notes.append(f"Transition out: {cs.transition_out}")

        if cs.visual_effects:
            notes.append(f"VFX: {', '.join(cs.visual_effects)}")

        return "; ".join(notes)

    def _suggest_layout(self, cs: CinematicShot) -> str:
        """Suggest visual layout based on shot type."""
        layouts = {
            "close": "centered, face fills upper third",
            "medium": "rule_of_thirds, character on left or right",
            "wide": "centered with environmental context",
            "drone": "symmetrical, subject centered",
            "pov": "immersive, leading lines to subject",
            "tracking": "dynamic diagonal composition",
            "dutch": "tilted composition, tension through asymmetry",
            "overhead": "top-down geometric composition",
            "two_shot": "split frame, characters on opposite thirds",
            "over_shoulder": "foreground shoulder out of focus, subject centered",
        }
        return layouts.get(cs.shot_type, layouts["medium"])

    def _suggest_layout_from_type(self, shot_type: str) -> str:
        """Suggest layout from shot type string."""
        layouts = {
            "close": "centered, face fills upper third",
            "medium": "rule_of_thirds, character on left or right",
            "wide": "centered with environmental context",
            "drone": "symmetrical, subject centered",
            "pov": "immersive, leading lines to subject",
            "tracking": "dynamic diagonal composition",
            "dutch": "tilted composition, tension through asymmetry",
            "overhead": "top-down geometric composition",
            "two_shot": "split frame, characters on opposite thirds",
            "over_shoulder": "foreground shoulder out of focus, subject centered",
        }
        return layouts.get(shot_type, layouts["medium"])

    def _timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
