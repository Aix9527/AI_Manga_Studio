"""
AI Manga Studio Pro V5 — Last Frame Generator

Intelligently generates the LAST FRAME (尾帧) for I2V video generation.

For Wan2.2 I2V, having both first and last frame enables:
- Smooth interpolation between key poses
- Precise motion control
- Cinematic shot continuity

This module:
1. Analyzes the action sequence of a shot
2. Determines the END STATE of the character/action
3. Generates a last-frame prompt that matches the first frame's character consistency
4. Builds a ComfyUI workflow to generate the last frame image
5. Ensures the last frame is compatible with the first frame (same character, same scene)
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.director_video_prompt_builder import (
    CinematicShot,
    DirectorVideoPromptBuilder,
    ACTION_MOTION_MAP,
)


# ============================================================
# Action End-State Mappings
# ============================================================

# Maps action keywords to their END STATE descriptions
ACTION_END_STATES = {
    "walk": "角色完成一步，身体略微前倾，一只脚在前一只脚在后，手臂自然摆动到相反位置",
    "run": "角色奔跑中腾空瞬间，身体大幅前倾，双臂大幅度摆动，头发衣物强烈后飘",
    "attack": "攻击命中后的收招姿态，身体前冲惯性，手臂保持攻击延伸姿势",
    "defend": "防御完成姿态，盾牌/手臂保持在防御位置，身体半蹲蓄力",
    "sit": "已坐定姿态，身体放松靠在椅面上，双手自然放置",
    "stand": "完全站直姿态，身体挺拔，双肩打开，目视前方",
    "gesture": "手势完成姿态，手臂保持指向或展示位置",
    "cast_spell": "施法完成姿态，手臂高举，魔法能量在手中汇聚或释放",
    "fight": "战斗连招中的一个定格姿态，身体处于攻防转换的中间态",
    "idle": "自然站立，轻微呼吸起伏，重心在一侧腿上",
    "embrace": "拥抱完成姿态，双臂环抱对方，身体贴近",
    "bow": "鞠躬完成姿态，上半身前倾约45度，双手放两侧或交叠",
    "draw_weapon": "武器已拔出，持武器手臂前伸或置于身侧准备姿态",
    "fall": "倒地姿态，身体躺在地面上",
    "jump": "跳跃到最高点或落地瞬间的姿态",
}

# Emotion-based facial end states
EMOTION_END_FACES = {
    "angry": "愤怒表情定格，眉头紧锁，眼神凶狠，嘴角下撇，面部肌肉紧绷",
    "sad": "悲伤表情定格，眼神低垂，眼眶微红，嘴角下垂，面部柔和",
    "happy": "开心表情定格，笑容灿烂，眼睛弯成月牙，面部舒展",
    "fearful": "恐惧表情定格，眼睛睁大，瞳孔收缩，嘴巴微张，面部僵硬",
    "surprised": "惊讶表情定格，眉毛高挑，眼睛圆睁，嘴巴呈O型",
    "tense": "紧张表情定格，咬紧牙关，颈部青筋微现，面部肌肉紧绷",
    "determined": "坚定表情定格，目光如炬，下巴微抬，嘴唇紧闭成直线",
    "calm": "平静表情定格，面容安详，眼神温和，嘴角微扬",
    "excited": "兴奋表情定格，眼睛发亮，嘴巴微张，面部肌肉活跃",
    "neutral": "自然表情定格，轻微眨眼，呼吸均匀",
}


# ============================================================
# Data Models
# ============================================================

@dataclass
class LastFrameSpec:
    """Specification for generating a last frame image."""
    shot_id: str = ""
    first_frame_prompt: str = ""
    last_frame_prompt: str = ""
    character_anchor: str = ""
    scene_anchor: str = ""
    action_end_state: str = ""
    expression_end_state: str = ""
    camera_end_state: str = ""
    lighting_end_state: str = ""
    resolution: List[int] = field(default_factory=lambda: [1344, 768])
    seed: int = -1
    steps: int = 30
    cfg: float = 5.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "first_frame_prompt": self.first_frame_prompt,
            "last_frame_prompt": self.last_frame_prompt,
            "character_anchor": self.character_anchor,
            "scene_anchor": self.scene_anchor,
            "action_end_state": self.action_end_state,
            "expression_end_state": self.expression_end_state,
            "camera_end_state": self.camera_end_state,
            "lighting_end_state": self.lighting_end_state,
            "resolution": self.resolution,
            "seed": self.seed,
            "steps": self.steps,
            "cfg": self.cfg,
        }


# ============================================================
# Last Frame Generator
# ============================================================

class LastFrameGenerator:
    """Generates last frame (尾帧) specifications for I2V video generation.

    The last frame is the END STATE of the shot — what the character/scene
    looks like after all actions and camera movements are complete.

    This ensures Wan2.2 I2V can smoothly interpolate between
    the first frame and the last frame.
    """

    def __init__(self):
        logger.info("LastFrameGenerator initialized (V5)")

    def generate_spec(
        self,
        cinematic_shot: CinematicShot,
        first_frame_prompt: str = "",
    ) -> LastFrameSpec:
        """Generate a last frame specification from a CinematicShot.

        Args:
            cinematic_shot: The shot with action, emotion, camera data.
            first_frame_prompt: The first frame prompt (for consistency).

        Returns:
            LastFrameSpec with all fields populated.
        """
        spec = LastFrameSpec(
            shot_id=cinematic_shot.shot_id,
            first_frame_prompt=first_frame_prompt,
            resolution=cinematic_shot.resolution if hasattr(cinematic_shot, "resolution") else [1344, 768],
        )

        # 1. Extract character anchor from first frame
        spec.character_anchor = self._extract_character_anchor(first_frame_prompt)

        # 2. Extract scene anchor
        spec.scene_anchor = self._extract_scene_anchor(cinematic_shot)

        # 3. Determine action end state
        spec.action_end_state = self._determine_action_end_state(cinematic_shot)

        # 4. Determine expression end state
        spec.expression_end_state = self._determine_expression_end_state(cinematic_shot)

        # 5. Determine camera end state
        spec.camera_end_state = self._determine_camera_end_state(cinematic_shot)

        # 6. Determine lighting end state
        spec.lighting_end_state = self._determine_lighting_end_state(cinematic_shot)

        # 7. Build last frame prompt
        spec.last_frame_prompt = self._assemble_last_frame_prompt(spec)

        logger.debug(
            f"LastFrameGenerator: spec for {spec.shot_id}, "
            f"action_end='{spec.action_end_state[:50]}...' "
        )
        return spec

    def generate_batch(
        self,
        shots: List[CinematicShot],
        first_frame_prompts: List[str],
    ) -> List[LastFrameSpec]:
        """Generate last frame specs for a batch of shots."""
        specs = []
        for shot, prompt in zip(shots, first_frame_prompts):
            specs.append(self.generate_spec(shot, prompt))
        logger.info(f"LastFrameGenerator: generated {len(specs)} last frame specs")
        return specs

    # ---- Internal Methods ----

    def _extract_character_anchor(self, first_frame_prompt: str) -> str:
        """Extract character description from first frame prompt."""
        if not first_frame_prompt:
            return ""

        # Heuristic: character descriptions typically contain
        # gender prefix + appearance details
        parts = []

        # Look for common character pattern markers
        import re
        gender_patterns = [
            r"(1girl|1boy|1character)\s*,?\s*(.+?)(?=,?\s*(wearing|with|standing|featuring|posing|expression))",
        ]

        for pattern in gender_patterns:
            match = re.search(pattern, first_frame_prompt, re.IGNORECASE)
            if match:
                parts.append(match.group(0))
                break

        # If no regex match, take first 200 chars as character anchor
        if not parts and len(first_frame_prompt) > 50:
            parts.append(first_frame_prompt[:200])

        return ", ".join(parts) if parts else first_frame_prompt[:300]

    def _extract_scene_anchor(self, shot: CinematicShot) -> str:
        """Extract scene description from shot data."""
        parts = []
        if shot.scene_description:
            parts.append(shot.scene_description)
        if shot.weather and shot.weather != "clear":
            parts.append(f"{shot.weather} weather")
        if shot.time_of_day:
            parts.append(f"{shot.time_of_day} time")
        return ", ".join(parts) if parts else "simple background"

    def _determine_action_end_state(self, shot: CinematicShot) -> str:
        """Determine the end state of character actions."""
        if not shot.character_actions:
            return "角色保持当前姿态，仅有轻微呼吸起伏"

        # Use the last action's end state
        last_action = shot.character_actions[-1]
        end_state = ACTION_END_STATES.get(last_action.lower(), "")

        if not end_state:
            # Generic: action completed
            mapped = ACTION_MOTION_MAP.get(last_action.lower(), last_action)
            end_state = f"{mapped}的结束姿态，身体保持动作终点位置"

        return end_state

    def _determine_expression_end_state(self, shot: CinematicShot) -> str:
        """Determine the end facial expression."""
        if shot.expressions:
            return shot.expressions[-1]

        return EMOTION_END_FACES.get(shot.emotion, "自然表情定格")

    def _determine_camera_end_state(self, shot: CinematicShot) -> str:
        """Determine camera end position/state."""
        if shot.camera_movement:
            # Camera ends at the final position of its movement
            return f"镜头完成{shot.camera_movement}后停留在最终位置"

        # Default: camera settled
        return "镜头稳定在最终构图位置"

    def _determine_lighting_end_state(self, shot: CinematicShot) -> str:
        """Determine lighting end state."""
        if shot.custom_lighting:
            return shot.custom_lighting

        # Same lighting throughout, possibly with subtle changes
        return "灯光保持场景设定，可能有微妙的光影变化"

    def _assemble_last_frame_prompt(self, spec: LastFrameSpec) -> str:
        """Assemble the complete last frame prompt."""
        parts = [
            spec.character_anchor,
            spec.action_end_state,
            spec.expression_end_state,
            spec.scene_anchor + "作为背景",
            spec.camera_end_state,
            spec.lighting_end_state,
        ]
        return "，".join(p for p in parts if p and p != spec.character_anchor)
