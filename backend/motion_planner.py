"""
AI Manga Studio Pro V3 — Cinema Motion Planner

根据 Shot 类型自动生成运动规划，不再依赖 Wan 自行推断运动。
输出结构化的运动计划供 Prompt Engine 和 Video Pipeline 使用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from loguru import logger


# ============================================================
# Data Classes
# ============================================================

@dataclass
class MotionPlan:
    """Structured motion plan for a single shot."""

    shot_id: str = ""
    camera_movement: str = ""       # e.g. "slow pan", "push in", "static"
    subject_motion: str = ""        # e.g. "slow walk", "turn head", "idle"
    expression: str = ""            # e.g. "blink", "slight smile", "neutral"
    cloth_motion: str = ""          # e.g. "light wind", "static"
    speed: str = "medium"           # ultra_slow / slow / medium / fast
    stabilize: bool = True
    interpolation_needed: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# Cinema Motion Planner
# ============================================================

class CinemaMotionPlanner:
    """根据 Shot 类型自动生成电影级运动规划。

    不调 LLM，纯粹基于模板 + 规则。输出 MotionPlan 供
    CinemaPromptEngine.build_video_prompt() 消费。
    """

    # ── Shot Type → Motion Template ──────────────────────────

    SHOT_MOTION_MAP: Dict[str, dict] = {
        "wide": {
            "camera": "slow pan",
            "speed": "slow",
            "stabilize": True,
            "subject_motion": "idle or slow walk",
            "expression": "neutral",
            "cloth_motion": "light wind",
            "interpolation_needed": True,
        },
        "medium": {
            "camera": "push in",
            "speed": "medium",
            "stabilize": True,
            "subject_motion": "slight body sway",
            "expression": "neutral",
            "cloth_motion": "static",
            "interpolation_needed": False,
        },
        "close-up": {
            "camera": "static",
            "speed": "slow",
            "stabilize": True,
            "subject_motion": "subtle head movement",
            "expression": "blink + micro-expression",
            "cloth_motion": "static",
            "interpolation_needed": False,
        },
        "action": {
            "camera": "tracking",
            "speed": "medium",
            "stabilize": True,
            "subject_motion": "dynamic action movement",
            "expression": "focused",
            "cloth_motion": "wind + motion blur",
            "interpolation_needed": True,
        },
        "dialogue": {
            "camera": "static + push in",
            "speed": "very slow",
            "stabilize": True,
            "subject_motion": "subtle gestures",
            "expression": "lip sync + micro-expression",
            "cloth_motion": "static",
            "interpolation_needed": False,
        },
        "over-shoulder": {
            "camera": "slow dolly",
            "speed": "slow",
            "stabilize": True,
            "subject_motion": "idle",
            "expression": "neutral",
            "cloth_motion": "static",
            "interpolation_needed": False,
        },
        "pov": {
            "camera": "handheld subtle shake",
            "speed": "slow",
            "stabilize": False,
            "subject_motion": "walking rhythm bounce",
            "expression": "neutral",
            "cloth_motion": "static",
            "interpolation_needed": False,
        },
        "tracking": {
            "camera": "tracking follow",
            "speed": "medium",
            "stabilize": True,
            "subject_motion": "continuous movement",
            "expression": "neutral",
            "cloth_motion": "wind",
            "interpolation_needed": True,
        },
        "dutch": {
            "camera": "static tilt",
            "speed": "slow",
            "stabilize": True,
            "subject_motion": "idle",
            "expression": "tense",
            "cloth_motion": "static",
            "interpolation_needed": False,
        },
        "aerial": {
            "camera": "drone fly-over",
            "speed": "slow",
            "stabilize": True,
            "subject_motion": "none (environmental)",
            "expression": "none",
            "cloth_motion": "none",
            "interpolation_needed": True,
        },
    }

    # ── Emotion → expression modifier ────────────────────────

    EMOTION_EXPRESSION_MAP: Dict[str, str] = {
        "neutral": "neutral expression, slight blink",
        "happy": "gentle smile, bright eyes, subtle laugh lines",
        "sad": "slight frown, downcast eyes, subtle tear glisten",
        "angry": "furrowed brows, tense jaw, narrowed eyes",
        "fearful": "wide eyes, slight tremble, shallow breathing",
        "surprised": "raised eyebrows, widened eyes, parted lips",
        "loving": "soft gaze, gentle smile, relaxed features",
        "worried": "furrowed brows, biting lip, glancing aside",
        "silent": "still expression, distant gaze, minimal movement",
        "sighing": "slow exhale, slight shoulder drop, relaxed",
        "trembling": "body tremble, shaking hands, unstable posture",
    }

    # ── Beat type → subject motion override ──────────────────

    BEAT_MOTION_HINT: Dict[str, str] = {
        "dialogue": "subtle gestures during speech, natural head nods",
        "action": "dynamic full-body movement, fast direction changes",
        "monologue": "minimal movement, introspective stillness, slow gestures",
        "transition": "environmental pan, no subject motion",
        "narration": "slow ambient movement, gentle sway",
    }

    # ── Public API ────────────────────────────────────────────

    def plan_motion(self, shot: Any) -> MotionPlan:
        """Generate motion plan from a Shot object.

        Args:
            shot: Shot object with camera, emotion, action, beat_type attributes.

        Returns:
            MotionPlan with structured motion fields.
        """
        camera = str(getattr(shot, "camera", "medium")).lower()
        emotion = str(getattr(shot, "emotion", "neutral")).lower()
        shot_id = str(getattr(shot, "shot_id", ""))

        # Resolve motion template
        template = self.SHOT_MOTION_MAP.get(
            camera,
            self.SHOT_MOTION_MAP["medium"],
        )

        # Build camera movement
        camera_movement = template.get("camera", "static")

        # Build subject motion: check beat motion hint first
        beat_type = str(getattr(shot, "beat_type", "")).lower()
        motion_hint = str(getattr(shot, "motion_hint", ""))
        if motion_hint:
            subject_motion = motion_hint
        elif beat_type and beat_type in self.BEAT_MOTION_HINT:
            subject_motion = self.BEAT_MOTION_HINT[beat_type]
        else:
            subject_motion = template.get("subject_motion", "idle")

        # Build expression from emotion
        expression = self.EMOTION_EXPRESSION_MAP.get(
            emotion,
            self.EMOTION_EXPRESSION_MAP["neutral"],
        )

        # Cloth motion
        cloth_motion = template.get("cloth_motion", "static")

        # Compose
        plan = MotionPlan(
            shot_id=shot_id,
            camera_movement=camera_movement,
            subject_motion=subject_motion,
            expression=expression,
            cloth_motion=cloth_motion,
            speed=template.get("speed", "medium"),
            stabilize=template.get("stabilize", True),
            interpolation_needed=template.get("interpolation_needed", False),
        )

        return plan

    def plan_batch(self, shots: List[Any]) -> List[MotionPlan]:
        """Generate motion plans for a batch of shots.

        Args:
            shots: List of Shot objects.

        Returns:
            List of MotionPlan, one per shot.
        """
        plans = []
        for shot in shots:
            plans.append(self.plan_motion(shot))

        logger.info(f"CinemaMotionPlanner: Generated {len(plans)} motion plans")
        return plans

    def to_dict(self, plan: MotionPlan) -> Dict[str, Any]:
        """Convert MotionPlan to dict for serialization / extra storage."""
        return {
            "shot_id": plan.shot_id,
            "camera_movement": plan.camera_movement,
            "subject_motion": plan.subject_motion,
            "expression": plan.expression,
            "cloth_motion": plan.cloth_motion,
            "speed": plan.speed,
            "stabilize": plan.stabilize,
            "interpolation_needed": plan.interpolation_needed,
        }
