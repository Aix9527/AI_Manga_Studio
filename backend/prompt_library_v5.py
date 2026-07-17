"""
AI Manga Studio Pro V5 — Director-Level Prompt Library

Comprehensive prompt templates for:
1. Image generation (人物三身图 + 分镜画面)
2. Video generation (导演级视频提示词)
3. Character consistency (人物一致性锁)
4. Scene/background generation
5. VFX/effect injection
6. Lighting design
7. Camera movement directions

All prompts follow the reference materials from:
- wan工作室爆量 prompt patterns
- sora工作室爆量 storyboard breakdown
- 最新镜头处理提示词 camera treatment
- 人物形象精细化反推 character design
- 动态漫反推 dynamic comic reverse
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger


# ============================================================
# Image Prompt Templates
# ============================================================

IMAGE_PROMPT_TEMPLATES = {
    # Character turnaround (三身图)
    "character_front": {
        "template": (
            "full body front view, {gender_prefix} featuring {name}, "
            "{hair_description}, {eye_description}, {face_description}, "
            "{clothing_description}, {body_description}, "
            "standing straight facing forward, both feet visible, "
            "complete body in frame, no duplicates, clean centered composition, "
            "{lighting_description}, {camera_description}, {style_tag}"
        ),
        "variables": ["name", "gender_prefix", "hair_description", "eye_description",
                      "face_description", "clothing_description", "body_description",
                      "lighting_description", "camera_description", "style_tag"],
    },
    "character_side": {
        "template": (
            "full body side profile view, {gender_prefix} featuring {name}, "
            "{hair_description}, {eye_description}, {face_description}, "
            "{clothing_description}, {body_description}, "
            "standing sideways, complete body silhouette, "
            "showing facial profile, one eye visible, "
            "no duplicates, clean centered composition, "
            "{lighting_description}, {camera_description}, {style_tag}"
        ),
    },
    "character_back": {
        "template": (
            "full body back view, {gender_prefix} featuring {name}, "
            "{hair_description} from behind, {clothing_description} rear view, "
            "{body_description}, "
            "standing facing away, complete body visible, "
            "showing back of head and rear clothing, "
            "no duplicates, clean centered composition, "
            "{lighting_description}, {camera_description}, {style_tag}"
        ),
    },
    # Shot-level image prompts
    "close_up": {
        "template": (
            "close-up portrait, {gender_prefix} featuring {name}, "
            "{hair_description}, {eye_description}, {expression_description}, "
            "{clothing_description} visible on shoulders, "
            "head and shoulders centered, shallow depth of field, "
            "bokeh background, {lighting_description}, "
            "85mm portrait lens, f/1.8, {style_tag}"
        ),
    },
    "medium_shot": {
        "template": (
            "waist-up portrait, {gender_prefix} featuring {name}, "
            "{hair_description}, {eye_description}, {expression_description}, "
            "{clothing_description}, {action_description}, "
            "centered standing, {scene_description} as environmental backdrop, "
            "50mm standard lens, f/2.8, {lighting_description}, {style_tag}"
        ),
    },
    "wide_shot": {
        "template": (
            "full body wide shot, {gender_prefix} featuring {name}, "
            "{hair_description}, {clothing_description}, {action_description}, "
            "{scene_description} as environmental backdrop, "
            "one complete figure standing centered, "
            "24mm wide lens, f/8, deep depth of field, {lighting_description}, {style_tag}"
        ),
    },
}


# ============================================================
# Video Prompt Templates
# ============================================================

VIDEO_PROMPT_TEMPLATES = {
    # Dialogue scene
    "dialogue": {
        "structure": (
            "0秒-0.15秒为固定废帧\n"
            "镜头{camera_movement}\n"
            "{name}表情{expression}\n"
            "对话：{dialogue}\n"
            "环境{environment_motion}\n"
            "灯光{lighting_behavior}\n"
            "动漫风格，逼真精细，光影真实，色彩自然"
        ),
        "elements": ["camera_movement", "name", "expression", "dialogue",
                     "environment_motion", "lighting_behavior"],
    },
    # Action scene
    "action": {
        "structure": (
            "0秒-0.15秒为固定废帧\n"
            "镜头{camera_movement}\n"
            "{name}{action_sequence}\n"
            "速度线{vfx_effects}\n"
            "冲击波{impact_effects}\n"
            "衣物{cloth_motion}\n"
            "灯光{lighting_behavior}\n"
            "动漫风格，逼真精细，高燃视觉，速度线，冲击波，高对比度阴影"
        ),
        "elements": ["camera_movement", "name", "action_sequence", "vfx_effects",
                     "impact_effects", "cloth_motion", "lighting_behavior"],
    },
    # Landscape/scenic
    "landscape": {
        "structure": (
            "0秒-0.15秒为固定废帧\n"
            "镜头{camera_movement}\n"
            "{scene_description}\n"
            "天气{weather_effects}\n"
            "云朵{cloud_motion}\n"
            "光线{lighting_behavior}\n"
            "动漫风格，逼真精细，光影真实，色彩自然"
        ),
        "elements": ["camera_movement", "scene_description", "weather_effects",
                     "cloud_motion", "lighting_behavior"],
    },
}


# ============================================================
# Negative Prompts
# ============================================================

NEGATIVE_PROMPTS = {
    "image_general": (
        "worst quality, low quality, blurry, jpeg artifacts, compression artifacts, "
        "deformed, distorted, disfigured, bad anatomy, extra limbs, missing limbs, "
        "fused fingers, too many fingers, long neck, extra arms, extra legs, "
        "ugly, duplicate, morbid, mutilated, poorly drawn face, mutation, blurry, "
        "watermark, text, logo, signature, banner, "
        "cropped, out of frame, cut off, partial view, "
        "wrong size, wrong scale, inconsistent proportions, "
        "multiple characters in one frame, overlapping bodies, "
        "floating limbs, disconnected hands, mismatched clothing, "
        "bad hands, missing fingers, extra digits, deformed fingers, "
        "asymmetric eyes, crossed eyes, mismatched pupils, "
        "flat lighting, overexposed, underexposed, harsh shadows, "
        "cartoonish, 3d render, plastic skin, doll-like, "
        "noise, grain, banding, artifacts, pixelation"
    ),
    "video_general": (
        "low quality, blurry, jitter, flickering, morphing, distortion, "
        "character inconsistency, body fragmentation, "
        "watermark, text, logo, signature, "
        "repeated frames, frozen motion, unnatural movement, "
        "disappearing limbs, floating objects, "
        "camera shake, unstable footage"
    ),
    "character_consistency": (
        "different outfit, inconsistent clothing, "
        "different hair color, different eye color, "
        "different face shape, different body type, "
        "extra characters, missing characters, "
        "duplicate characters, overlapping bodies"
    ),
}


# ============================================================
# Prompt Builder
# ============================================================

class PromptLibrary:
    """Central prompt library for the V5 pipeline.

    Provides:
    - Pre-built prompt templates for images and videos
    - Character consistency locking
    - Scene/environment templates
    - Lighting design templates
    - VFX effect templates
    - Camera movement directions
    """

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        logger.info("PromptLibrary initialized (V5)")

    def get_image_prompt(
        self,
        template_name: str,
        variables: Dict[str, str],
        style: str = "anime",
    ) -> str:
        """Get a formatted image prompt from the template library."""
        template = IMAGE_PROMPT_TEMPLATES.get(template_name)
        if not template:
            return variables.get("generic_prompt", "character portrait")

        # Fill template
        prompt = template["template"]
        for key, value in variables.items():
            prompt = prompt.replace("{" + key + "}", value or "")

        # Append style tag
        style_tags = {
            "anime": "anime style, cel shading, vibrant colors, clean lineart, masterpiece, best quality, 8K",
            "cinematic": "cinematic film still, anamorphic lens, color graded, film grain, dramatic lighting, 8K",
            "realistic": "photorealistic, detailed skin texture, subsurface scattering, natural lighting, 8K",
            "manga": "manga style, black and white, screentone, crosshatching, high contrast, ink lines",
            "semi_realistic": "semi-realistic, detailed rendering, soft shading, anime-inspired realism, 8K",
        }
        prompt += ", " + style_tags.get(style, style_tags["anime"])

        return prompt

    def get_video_prompt(
        self,
        template_name: str,
        variables: Dict[str, str],
    ) -> str:
        """Get a formatted video prompt from the template library."""
        template = VIDEO_PROMPT_TEMPLATES.get(template_name)
        if not template:
            return variables.get("generic_video_prompt", "character animation")

        prompt = template["structure"]
        for key, value in variables.items():
            prompt = prompt.replace("{" + key + "}", value or "")

        return prompt

    def get_negative_prompt(self, category: str = "image_general") -> str:
        """Get a negative prompt by category."""
        return NEGATIVE_PROMPTS.get(category, NEGATIVE_PROMPTS["image_general"])

    def build_character_anchor(
        self,
        name: str,
        gender: str,
        hair_style: str,
        hair_color: str,
        eye_color: str,
        clothing: str,
        body_type: str,
    ) -> str:
        """Build a character anchor string for consistency locking."""
        parts = []

        # Gender prefix
        if gender in ("female", "girl", "woman"):
            parts.append("1girl")
        elif gender in ("male", "boy", "man"):
            parts.append("1boy")
        else:
            parts.append("1character")

        parts.append(f"featuring {name}")

        if hair_color:
            parts.append(f"{hair_color} hair")
        if hair_style:
            parts.append(f"{hair_style} hairstyle")
        if eye_color:
            parts.append(f"{eye_color} eyes")
        if body_type:
            parts.append(f"{body_type} body type")
        if clothing:
            parts.append(f"wearing {clothing}")

        return ", ".join(parts)

    def build_scene_anchor(
        self,
        scene_name: str,
        time_of_day: str,
        weather: str,
    ) -> str:
        """Build a scene anchor string."""
        parts = [scene_name]
        if time_of_day:
            parts.append(f"{time_of_day} time")
        if weather and weather != "clear":
            parts.append(f"{weather} weather")
        return ", ".join(parts)

    def get_camera_direction(self, movement_key: str) -> Dict[str, str]:
        """Get camera direction by key."""
        from backend.director_video_prompt_builder import CAMERA_MOVEMENTS
        return CAMERA_MOVEMENTS.get(movement_key, {
            "cn": "镜头保持稳定",
            "en": "camera remains stable",
        })

    def get_lighting_direction(self, preset_key: str) -> Dict[str, str]:
        """Get lighting direction by preset key."""
        from backend.director_video_prompt_builder import LIGHTING_PRESETS
        return LIGHTING_PRESETS.get(preset_key, LIGHTING_PRESETS.get("morning", {}))

    def get_vfx_effects(self, emotion: str) -> List[str]:
        """Get VFX effects by emotion."""
        from backend.director_video_prompt_builder import EMOTION_VFX_MAP
        vfx = EMOTION_VFX_MAP.get(emotion, {})
        if isinstance(vfx, dict):
            return [vfx.get("cn", "")]
        return [str(vfx)]

    def get_action_motion(self, action_key: str) -> str:
        """Get action motion description."""
        from backend.director_video_prompt_builder import ACTION_MOTION_MAP
        return ACTION_MOTION_MAP.get(action_key, action_key)
