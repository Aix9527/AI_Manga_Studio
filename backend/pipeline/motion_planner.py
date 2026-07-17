"""
V3.0 Layer 11 — Motion Planner

Generates MotionPlan from Beat and Scene context for video generation.
The MotionPlan is injected into Wan2.2 / Hunyuan / LTX workflows
to control camera movement, environmental effects, and character motion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MotionPlan:
    """Video motion parameters for a single shot."""

    shot_id: str = ""

    # Camera
    camera_movement: str = "static"
    # "push_in" / "pull_out" / "pan_left" / "pan_right"
    # "tilt_up" / "tilt_down" / "static" / "dolly_zoom" / "arc" / "tracking"

    speed: str = "medium"
    # "slow" / "medium" / "fast"

    # Environment
    wind: str = "none"
    # "none" / "low" / "medium" / "high"

    # Character motion
    blink: str = "yes"
    # "yes" / "no"

    cloth_movement: str = "none"
    # "none" / "subtle" / "flowing"

    hair_movement: str = "none"
    # "none" / "gentle" / "windy"

    # Effects
    particle_effects: str = "none"
    # "none" / "dust" / "rain" / "snow" / "leaves" / "sparks"

    # Focus
    focus_shift: str = "none"
    # "none" / "rack_focus" / "follow"

    # Metadata
    duration: float = 2.0
    description: str = ""


# ── Camera dictionary ─────────────────────────────────────────

_CAMERA_SELECTION: Dict[str, List[str]] = {
    "dialogue": ["static", "push_in", "pull_out"],
    "action": ["pan_left", "pan_right", "tracking", "dolly_zoom"],
    "emotional": ["push_in", "tilt_up", "static"],
    "introduction": ["pan_right", "arc", "static"],
    "transition": ["pan_left", "pan_right", "arc"],
    "reveal": ["pull_out", "arc", "tilt_up"],
    "intense": ["tracking", "dolly_zoom", "push_in"],
    "calm": ["static", "pan_left", "pan_right"],
}


class MotionPlanner:
    """Automatically generates MotionPlan from narrative context.

    Decision logic:
      - Beat type → camera movement family
      - Emotion → speed and focus
      - Scene weather → environmental effects
      - Action intensity → cloth/hair movement

    Usage:
        planner = MotionPlanner()
        plan = planner.plan_from_beat(beat, scene_context, emotion)
        wan_params = MotionPlanner.to_wan_params(plan)
    """

    @staticmethod
    def plan_from_beat(
        beat: Any,
        scene_context: Any,
        emotion: str = "",
    ) -> MotionPlan:
        """Generate a MotionPlan from beat and scene context.

        Args:
            beat: Beat data (has type, action, emotion).
            scene_context: Scene context (has weather, location, time).
            emotion: Override emotion string.

        Returns:
            MotionPlan ready for video generation.
        """
        plan = MotionPlan()

        # Extract fields
        beat_type = getattr(beat, "beat_type", "") if beat else ""
        beat_description = getattr(beat, "description", "") if beat else ""
        beat_emotion = getattr(beat, "emotion", "") if beat else ""
        emotion = emotion or beat_emotion

        # Weather from scene context
        weather = ""
        if scene_context:
            weather = (
                getattr(scene_context, "weather", "")
                if hasattr(scene_context, "weather")
                else scene_context.get("weather", "")
                if isinstance(scene_context, dict)
                else ""
            )

        # ── Camera ──────────────────────────────────────
        plan.camera_movement = MotionPlanner._pick_camera(beat_type, emotion)
        plan.speed = MotionPlanner._pick_speed(emotion)

        # ── Environment ─────────────────────────────────
        plan.wind = MotionPlanner._pick_wind(weather, emotion)
        plan.particle_effects = MotionPlanner._pick_particles(weather, emotion)

        # ── Character motion ────────────────────────────
        plan.blink = "yes"
        action_intensity = MotionPlanner._action_intensity(beat_description)
        if action_intensity > 0.5:
            plan.cloth_movement = "flowing"
            plan.hair_movement = "windy"
        elif action_intensity > 0.2:
            plan.cloth_movement = "subtle"
            plan.hair_movement = "gentle"
        else:
            plan.cloth_movement = "none"
            plan.hair_movement = "none"

        # ── Focus ───────────────────────────────────────
        plan.focus_shift = MotionPlanner._pick_focus(beat_type, emotion)

        plan.description = beat_description
        return plan

    @staticmethod
    def to_wan_params(plan: MotionPlan) -> dict:
        """Convert MotionPlan to Wan2.2 API parameters."""
        return {
            "camera_movement": plan.camera_movement,
            "speed": plan.speed,
            "wind": plan.wind,
            "blink": plan.blink,
            "cloth_movement": plan.cloth_movement,
            "hair_movement": plan.hair_movement,
            "particle_effects": plan.particle_effects,
            "focus_shift": plan.focus_shift,
            "duration": plan.duration,
        }

    # ── Selection helpers ─────────────────────────────────────

    @staticmethod
    def _pick_camera(beat_type: str, emotion: str) -> str:
        """Pick camera movement based on beat type and emotion."""
        import random

        candidates = _CAMERA_SELECTION.get(beat_type, ["static"])

        # Emotion override: emotional beats push in
        emotion_lower = emotion.lower()
        if "sad" in emotion_lower or "悲伤" in emotion_lower:
            candidates = ["push_in"]
        elif "angry" in emotion_lower or "愤怒" in emotion_lower:
            candidates = ["tracking", "dolly_zoom"]

        return random.choice(candidates) if candidates else "static"

    @staticmethod
    def _pick_speed(emotion: str) -> str:
        """Pick camera speed based on emotion."""
        fast_emotions = ["angry", "愤怒", "紧张", "action", "战斗"]
        slow_emotions = ["sad", "悲伤", "calm", "平静", "romantic", "温馨"]

        emotion_lower = emotion.lower()
        if any(e in emotion_lower for e in fast_emotions):
            return "fast"
        if any(e in emotion_lower for e in slow_emotions):
            return "slow"
        return "medium"

    @staticmethod
    def _pick_wind(weather: str, emotion: str) -> str:
        """Pick wind level based on weather and emotion."""
        weather_lower = weather.lower()
        if any(kw in weather_lower for kw in ["storm", "typhoon", "暴风", "台风"]):
            return "high"
        if any(kw in weather_lower for kw in ["wind", "breezy", "风"]):
            return "medium"
        if any(kw in emotion.lower() for kw in ["angry", "愤怒", "紧张"]):
            return "low"
        return "none"

    @staticmethod
    def _pick_particles(weather: str, emotion: str) -> str:
        """Pick particle effects based on weather and emotion."""
        weather_lower = weather.lower()
        if "雨" in weather_lower or "rain" in weather_lower:
            return "rain"
        if "雪" in weather_lower or "snow" in weather_lower:
            return "snow"
        if "雾" in weather_lower or "fog" in weather_lower:
            return "dust"
        if any(kw in weather_lower for kw in ["autumn", "autumn", "秋"]):
            return "leaves"
        return "none"

    @staticmethod
    def _pick_focus(beat_type: str, emotion: str) -> str:
        """Pick focus shift based on beat type and emotion."""
        if beat_type == "emotional":
            return "rack_focus"
        if beat_type == "action":
            return "follow"
        return "none"

    @staticmethod
    def _action_intensity(description: str) -> float:
        """Estimate action intensity from text."""
        t = description.lower()
        high = ["fight", "battle", "run", "slash", "blast", "打斗", "战斗", "奔跑"]
        medium = ["walk", "turn", "stand", "point", "行走", "转身"]

        if any(kw in t for kw in high):
            return 0.8
        if any(kw in t for kw in medium):
            return 0.3
        return 0.0
