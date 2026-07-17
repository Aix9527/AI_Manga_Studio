"""
AI Manga Studio V3.5 — Camera Planner

Intelligent camera angle and movement planner.
Source: 最新镜头处理提示词.txt

Key rules:
- 14 shots per 1000 words
- Shot types: 中景/近景/特写/大特写/全景/双人中景
- Camera movements: 推/拉/摇/跟/俯拍/仰拍/OTS/手持晃动
- Dynamic effects based on emotion intensity
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────

SHOT_TYPES: Tuple[str, ...] = ("中景", "近景", "特写", "大特写", "全景", "双人中景")

CAMERA_MOVEMENTS: Dict[str, str] = {
    "推": "dolly_in",
    "拉": "dolly_out",
    "摇": "pan",
    "跟": "tracking",
    "俯拍": "high_angle",
    "仰拍": "low_angle",
    "OTS": "over_the_shoulder",
    "手持晃动": "handheld_shake",
}

DEPTH_OF_FIELD: Tuple[str, ...] = ("深景深", "浅景深")

ANGLES: Tuple[str, ...] = ("平视", "俯视", "仰视")

DYNAMIC_EFFECTS: Tuple[str, ...] = (
    "速度线",
    "冲击波",
    "环境碎裂",
    "流光溢彩",
    "高对比度阴影",
)


# ── Data Models ───────────────────────────────────────────────

@dataclass
class CameraConfig:
    """Camera configuration for a single shot."""
    shot_id: str = ""
    shot_type: str = "中景"                # 中景/近景/特写/大特写/全景/双人中景
    camera_movement: str = "推"            # 推/拉/摇/跟/俯拍/仰拍/OTS/手持晃动
    depth_of_field: str = "深景深"         # 深景深/浅景深
    angle: str = "平视"                    # 平视/俯视/仰视
    dynamic_effect: str = ""               # 速度线/冲击波/环境碎裂/流光溢彩/高对比度阴影
    reason: str = ""                       # Why this configuration was chosen

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "shot_type": self.shot_type,
            "camera_movement": self.camera_movement,
            "depth_of_field": self.depth_of_field,
            "angle": self.angle,
            "dynamic_effect": self.dynamic_effect,
            "reason": self.reason,
        }


# ── Engine ────────────────────────────────────────────────────

class CameraPlanner:
    """Automatic camera angle and movement planner.

    Analyzes scene description, emotion intensity, and character count
    to determine optimal camera configuration for each shot.
    """

    # Emotion → preferred shot type mapping
    EMOTION_SHOT_MAP: Dict[str, str] = {
        "intense": "特写",      # High emotion → close-up
        "angry": "特写",
        "romantic": "双人中景",
        "sad": "近景",
        "action": "中景",
        "dialogue": "双人中景",
        "reveal": "全景",
        "suspense": "特写",
        "neutral": "中景",
    }

    # Emotion intensity → dynamic effect
    INTENSITY_EFFECT_MAP: Dict[str, str] = {
        "high": "冲击波",
        "medium": "速度线",
        "low": "",
    }

    def __init__(self) -> None:
        logger.info("CameraPlanner initialized (V3.5)")

    # ── Public API ────────────────────────────────────────

    def plan(
        self,
        scene_description: str,
        emotion_intensity: str = "neutral",
        character_count: int = 1,
    ) -> CameraConfig:
        """Plan camera configuration for a single shot.

        Args:
            scene_description: Text description of the scene.
            emotion_intensity: "high" / "medium" / "low" / "neutral".
            character_count: Number of characters in the shot.

        Returns:
            CameraConfig with recommended settings.
        """
        shot_type = self._infer_shot_type(scene_description, emotion_intensity, character_count)
        camera_movement = self._infer_movement(scene_description, emotion_intensity)
        depth_of_field = self._infer_dof(character_count, shot_type)
        angle = self._infer_angle(scene_description, character_count)
        dynamic_effect = self._infer_dynamic_effect(emotion_intensity)

        reason = self._build_reason(
            shot_type, camera_movement, emotion_intensity, character_count
        )

        config = CameraConfig(
            shot_type=shot_type,
            camera_movement=camera_movement,
            depth_of_field=depth_of_field,
            angle=angle,
            dynamic_effect=dynamic_effect,
            reason=reason,
        )

        logger.debug(
            f"CameraPlanner: shot_type={shot_type}, movement={camera_movement}, "
            f"dof={depth_of_field}, angle={angle}, effect={dynamic_effect}"
        )
        return config

    def plan_batch(
        self,
        shots: List[Dict[str, Any]],
    ) -> List[CameraConfig]:
        """Plan camera for multiple shots with continuity awareness.

        Args:
            shots: List of shot data dicts, each containing at minimum:
                   shot_id, scene_desc, and optionally emotion_intensity, character_count.

        Returns:
            List of CameraConfig, one per shot, with camera continuity between shots.
        """
        configs: List[CameraConfig] = []
        prev_movement: str = ""

        for shot in shots:
            config = self.plan(
                scene_description=shot.get("scene_desc", ""),
                emotion_intensity=shot.get("emotion_intensity", "neutral"),
                character_count=shot.get("character_count", 1),
            )
            config.shot_id = shot.get("shot_id", "")

            # Ensure camera movement variety — avoid repeating the same movement
            if config.camera_movement == prev_movement and len(CAMERA_MOVEMENTS) > 1:
                # Pick a different movement
                movements = [m for m in CAMERA_MOVEMENTS if m != prev_movement]
                import random
                config.camera_movement = random.choice(movements)

            prev_movement = config.camera_movement
            configs.append(config)

        logger.info(f"CameraPlanner: planned {len(configs)} camera configs")
        return configs

    @staticmethod
    def shots_per_1000_words(word_count: int) -> int:
        """Calculate target number of shots based on word count."""
        return max(1, round(word_count / 1000 * 14))

    # ── Internal inference methods ────────────────────────

    def _infer_shot_type(
        self,
        scene_desc: str,
        emotion_intensity: str,
        character_count: int,
    ) -> str:
        """Infer best shot type from scene context."""
        # Check scene description for clues
        desc_lower = scene_desc.lower()

        if any(kw in desc_lower for kw in ["对视", "对话", "交谈", "对峙", "两人"]):
            return "双人中景"
        if character_count >= 3:
            return "全景"
        if any(kw in desc_lower for kw in ["眼睛", "眼神", "瞳孔", "手指", "手"]):
            return "特写"
        if any(kw in desc_lower for kw in ["全身", "走来", "站立", "大门", "广场"]):
            return "全景"
        if character_count == 1:
            if emotion_intensity in ("high", "medium"):
                return "近景"
            return "中景"

        return "中景"

    def _infer_movement(self, scene_desc: str, emotion_intensity: str) -> str:
        """Infer camera movement."""
        desc_lower = scene_desc.lower()

        if any(kw in desc_lower for kw in ["跑", "追", "跟", "走", "移动"]):
            return "跟"
        if any(kw in desc_lower for kw in ["俯视", "从上", "鸟瞰", "高空"]):
            return "俯拍"
        if any(kw in desc_lower for kw in ["仰视", "仰望", "抬头", "天空"]):
            return "仰拍"
        if emotion_intensity == "high":
            return "推"
        if any(kw in desc_lower for kw in ["转", "环顾", "四周"]):
            return "摇"

        return "推"  # Default: slow push-in

    def _infer_dof(self, character_count: int, shot_type: str) -> str:
        """Infer depth of field."""
        if shot_type in ("特写", "大特写"):
            return "浅景深"
        if character_count >= 3:
            return "深景深"
        return "浅景深"

    def _infer_angle(self, scene_desc: str, character_count: int) -> str:
        """Infer camera angle."""
        desc_lower = scene_desc.lower()
        if any(kw in desc_lower for kw in ["俯视", "鸟瞰", "高空", "低头"]):
            return "俯视"
        if any(kw in desc_lower for kw in ["仰视", "仰望", "仰望天空"]):
            return "仰视"
        return "平视"

    def _infer_dynamic_effect(self, emotion_intensity: str) -> str:
        """Map emotion intensity to dynamic visual effect."""
        return self.INTENSITY_EFFECT_MAP.get(emotion_intensity, "")

    def _build_reason(
        self,
        shot_type: str,
        movement: str,
        emotion_intensity: str,
        character_count: int,
    ) -> str:
        """Generate human-readable reasoning."""
        parts = [f"选择{shot_type}景别"]
        if character_count == 2:
            parts.append("因双人场景")
        if emotion_intensity == "high":
            parts.append(f"情绪激烈→{movement}运镜")
        return "，".join(parts)
