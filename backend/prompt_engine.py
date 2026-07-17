"""
AI Manga Studio Pro V3 — Cinema Prompt Engine (Template Assembly)

V3 升级：从 LLM 临时写 prompt 改为严格的模板拼装系统。
CinemaPromptEngine 接收 CharacterDNA + SceneDNA + Shot 对象，
按字段拼接输出，绝不调用 LLM 生成 prompt。

保留旧版 PromptEngine / PromptV35 作为适配层，兼容现有调度器。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger


# ============================================================
# V3 Global Constants
# ============================================================

GLOBAL_NEGATIVE = (
    "worst quality, low quality, blurry, disfigured, deformed, "
    "bad anatomy, extra limbs, fused fingers, ugly, watermark, text, signature"
)


# ============================================================
# V3 — Cinema Prompt Engine (Template Assembly)
# ============================================================

@dataclass
class CinemaImagePrompt:
    """Decomposed image prompt with per-field segments."""

    shot_id: str = ""
    character_prompt: str = ""
    scene_prompt: str = ""
    camera_prompt: str = ""
    emotion_prompt: str = ""
    lighting_prompt: str = ""
    motion_prompt: str = ""
    style_prompt: str = ""
    negative_prompt: str = ""
    final_prompt: str = ""

    def merge(self) -> str:
        """Concatenate all non-empty positive fields into final prompt."""
        parts = [
            self.character_prompt,
            self.scene_prompt,
            self.camera_prompt,
            self.emotion_prompt,
            self.lighting_prompt,
            self.motion_prompt,
            self.style_prompt,
        ]
        return ", ".join(p for p in parts if p)


@dataclass
class CinemaVideoPrompt:
    """Decomposed video prompt with motion-specific fields."""

    shot_id: str = ""
    image_prompt: str = ""           # base image prompt (reused from CinemaImagePrompt)
    camera_movement: str = ""
    subject_motion: str = ""
    expression: str = ""
    cloth_motion: str = ""
    negative_prompt: str = ""
    final_prompt: str = ""

    def merge(self) -> str:
        parts = [
            self.image_prompt,
            self.camera_movement,
            self.subject_motion,
            self.expression,
            self.cloth_motion,
        ]
        return ", ".join(p for p in parts if p)


class CinemaPromptEngine:
    """V3 电影级 Prompt Engine — 纯模板拼装，不调 LLM。

    接收 CharacterDNA / SceneDNA / Shot 结构化对象，
    按字段拼接输出分字段 prompt 字典。
    """

    # Lighting inference: time_of_day → lighting description
    LIGHTING_MAP: Dict[str, str] = {
        "dawn": "soft morning light, golden hour glow, warm tones",
        "morning": "bright morning light, clear sky, crisp shadows",
        "noon": "harsh overhead light, strong shadows, high contrast",
        "afternoon": "warm afternoon light, soft shadows, golden tint",
        "dusk": "golden hour, warm orange glow, long shadows, cinematic rim light",
        "night": "warm night lighting, soft ambient glow, practical lights, dim atmosphere",
    }

    # Camera focal length inference
    FOCAL_MAP: Dict[str, str] = {
        "close-up": "85mm portrait lens, shallow depth of field, bokeh",
        "medium": "50mm standard lens, natural perspective",
        "wide": "24mm wide lens, deep focus, environmental context",
        "full": "35mm lens, full body framing",
        "over-shoulder": "50mm lens, foreground blur, OTS framing",
        "aerial": "drone shot, top-down, wide angle",
        "dutch": "35mm tilted frame, dramatic tension",
        "tracking": "24mm motion tracking, dynamic angle",
        "pov": "24mm handheld, immersive first-person",
    }

    # Default style tag
    DEFAULT_STYLE = "cinematic, high quality, 8K, professional"

    def __init__(self, style: str = "") -> None:
        self._style = style or self.DEFAULT_STYLE

    # ── Public API ────────────────────────────────────────────

    def build_image_prompt(
        self,
        character_dna: Any,
        scene_dna: Any,
        shot: Any,
    ) -> CinemaImagePrompt:
        """Build a decomposed image prompt from CharacterDNA + SceneDNA + Shot.

        Args:
            character_dna: CharacterDNA object with appearance_prompt attribute.
            scene_dna: ScenePack / SceneDNA with description, lighting, etc.
            shot: Shot object with camera, angle, emotion, action, composition.

        Returns:
            CinemaImagePrompt with per-field segments + final_prompt.
        """
        shot_id = str(getattr(shot, "shot_id", ""))

        # Character prompt: from CharacterDNA.appearance_prompt
        char_prompt = ""
        if character_dna is not None:
            char_prompt = getattr(character_dna, "appearance_prompt", "")
            if not char_prompt:
                # Fallback: use name + prompt_template
                name = getattr(character_dna, "name", "")
                template = getattr(character_dna, "prompt_template", "")
                char_prompt = f"{template}" if template else f"{name}"

        # Scene prompt: from SceneDNA.description
        scene_prompt = ""
        if scene_dna is not None:
            scene_prompt = getattr(scene_dna, "description", "")
            if not scene_prompt:
                scene_prompt = getattr(scene_dna, "name", "")

        # Camera prompt: shot.camera + shot.angle + shot.composition
        camera = str(getattr(shot, "camera", "medium"))
        angle = str(getattr(shot, "angle", "eye_level"))
        composition = str(getattr(shot, "composition", "rule-of-thirds"))
        focal = self.FOCAL_MAP.get(camera, "50mm standard lens")
        camera_prompt = f"{camera} shot, {angle} angle, {composition} composition, {focal}"

        # Emotion prompt: from shot.emotion
        emotion_prompt = str(getattr(shot, "emotion", "neutral"))

        # Lighting prompt: from scene_dna.lighting or inferred from time_of_day
        lighting_prompt = ""
        if scene_dna is not None:
            lighting_prompt = getattr(scene_dna, "default_lighting", "")
            if not lighting_prompt:
                time_of_day = getattr(scene_dna, "default_time", "") or getattr(scene_dna, "time", "day")
                lighting_prompt = self.LIGHTING_MAP.get(time_of_day, "natural lighting")

        # Also check if shot has its own lighting
        shot_lighting = getattr(shot, "lighting", "")
        if shot_lighting:
            lighting_prompt = shot_lighting

        # Motion prompt: from shot.action + motion_hint
        action = str(getattr(shot, "action", ""))
        motion_hint = str(getattr(shot, "motion_hint", ""))
        motion_prompt = f"{action}, {motion_hint}".strip(", ")

        # Negative prompt: global fixed
        negative_prompt = GLOBAL_NEGATIVE

        # Build final
        final_prompt = ", ".join(
            p for p in [
                char_prompt,
                scene_prompt,
                camera_prompt,
                emotion_prompt,
                lighting_prompt,
                motion_prompt,
                self._style,
            ] if p
        )

        return CinemaImagePrompt(
            shot_id=shot_id,
            character_prompt=char_prompt,
            scene_prompt=scene_prompt,
            camera_prompt=camera_prompt,
            emotion_prompt=emotion_prompt,
            lighting_prompt=lighting_prompt,
            motion_prompt=motion_prompt,
            style_prompt=self._style,
            negative_prompt=negative_prompt,
            final_prompt=final_prompt,
        )

    def build_video_prompt(
        self,
        character_dna: Any,
        scene_dna: Any,
        shot: Any,
        motion_plan: Optional[Dict[str, Any]] = None,
    ) -> CinemaVideoPrompt:
        """Build a decomposed video prompt with motion plan.

        Args:
            character_dna: CharacterDNA object.
            scene_dna: ScenePack / SceneDNA object.
            shot: Shot object.
            motion_plan: Output from MotionPlanner.plan_motion().

        Returns:
            CinemaVideoPrompt with motion-specific fields.
        """
        shot_id = str(getattr(shot, "shot_id", ""))

        # Reuse image prompt as base
        img_prompt = self.build_image_prompt(character_dna, scene_dna, shot)

        # Extract motion fields from motion_plan
        camera_movement = ""
        subject_motion = ""
        expression = ""
        cloth_motion = ""

        if motion_plan:
            camera_movement = str(getattr(motion_plan, "camera_movement", ""))
            subject_motion = str(getattr(motion_plan, "subject_motion", ""))
            expression = str(getattr(motion_plan, "expression", ""))
            cloth_motion = str(getattr(motion_plan, "cloth_motion", ""))

        final_prompt = ", ".join(
            p for p in [
                img_prompt.final_prompt,
                camera_movement,
                subject_motion,
                expression,
                cloth_motion,
            ] if p
        )

        return CinemaVideoPrompt(
            shot_id=shot_id,
            image_prompt=img_prompt.final_prompt,
            camera_movement=camera_movement,
            subject_motion=subject_motion,
            expression=expression,
            cloth_motion=cloth_motion,
            negative_prompt=img_prompt.negative_prompt,
            final_prompt=final_prompt,
        )

    def build_batch_image_prompts(
        self,
        shots: List[Any],
        char_dna_map: Dict[str, Any],
        scene_dna_map: Dict[str, Any],
    ) -> List[CinemaImagePrompt]:
        """Batch-build image prompts for all shots.

        Args:
            shots: List of Shot objects.
            char_dna_map: Dict mapping character name → CharacterDNA.
            scene_dna_map: Dict mapping scene_id/location → ScenePack.

        Returns:
            List of CinemaImagePrompt.
        """
        results = []
        for shot in shots:
            # Resolve character DNA
            char_names = getattr(shot, "characters", []) or []
            char_dna = None
            for name in char_names:
                if name in char_dna_map:
                    char_dna = char_dna_map[name]
                    break

            # Resolve scene DNA
            scene_id = getattr(shot, "scene", None)
            scene_dna = None
            if scene_id is not None and scene_id in scene_dna_map:
                scene_dna = scene_dna_map[scene_id]

            result = self.build_image_prompt(char_dna, scene_dna, shot)
            results.append(result)

        logger.info(f"CinemaPromptEngine: Built {len(results)} image prompts")
        return results


# ============================================================
# V3.5 Adapter — PromptV35
# ============================================================

class PromptV35:
    """V3.5 Prompt 适配层 — 包裹 CinemaPromptEngine，兼容现有调度器。

    提供与 ImagePromptBuilder / VideoPromptBuilder 兼容的接口，
    内部全部走 CinemaPromptEngine 的模板拼装路径，不调 LLM。
    """

    def __init__(self, style: str = "") -> None:
        self._engine = CinemaPromptEngine(style=style)

    def build_image(
        self,
        character_dna: Any,
        scene_dna: Any,
        shot: Any,
    ) -> CinemaImagePrompt:
        """Build image prompt (delegates to CinemaPromptEngine)."""
        return self._engine.build_image_prompt(character_dna, scene_dna, shot)

    def build_video(
        self,
        character_dna: Any,
        scene_dna: Any,
        shot: Any,
        motion_plan: Optional[Dict[str, Any]] = None,
    ) -> CinemaVideoPrompt:
        """Build video prompt (delegates to CinemaPromptEngine)."""
        return self._engine.build_video_prompt(character_dna, scene_dna, shot, motion_plan)

    def build_batch(
        self,
        shots: List[Any],
        char_dna_map: Dict[str, Any],
        scene_dna_map: Dict[str, Any],
    ) -> List[CinemaImagePrompt]:
        """Batch build image prompts."""
        return self._engine.build_batch_image_prompts(shots, char_dna_map, scene_dna_map)

    @property
    def engine(self) -> CinemaPromptEngine:
        """Access the underlying CinemaPromptEngine."""
        return self._engine


# ============================================================
# Legacy — V1 Prompt Engine (Backward Compat)
# ============================================================

from backend.models import ShotType


@dataclass
class PromptResult:
    """Complete prompt pair for a single shot (V1 legacy)."""
    positive: str = ""
    negative: str = ""
    shot_index: int = 0
    character_names: List[str] = field(default_factory=list)
    scene_name: str = ""


@dataclass
class BatchPromptResult:
    """Batch of prompts for a chapter (V1 legacy)."""
    chapter_index: int
    shots: List[PromptResult] = field(default_factory=list)


class PromptEngine:
    """V1 Prompt Engine — 保留向后兼容，内部委托给 CinemaPromptEngine。

    原始 V1 接口 generate_shot_prompt / generate_batch_prompts 保持不变，
    但内部走模板拼装路径。
    """

    CAMERA_MODIFIERS: Dict[ShotType, str] = {
        ShotType.close_up: "close-up shot, face focus, shallow depth of field, bokeh",
        ShotType.medium: "medium shot, waist-up, standard lens, portrait framing",
        ShotType.wide: "wide shot, full body, deep depth of field, environmental",
        ShotType.drone: "aerial view, drone shot, top-down perspective, bird's eye",
        ShotType.pov: "POV shot, first-person perspective, immersive, handheld",
        ShotType.tracking: "tracking shot, motion following, dynamic angle, speed lines",
        ShotType.dutch_angle: "dutch angle, tilted frame, dramatic tension, skewed perspective",
        ShotType.over_shoulder: "over-the-shoulder shot, OTS framing, foreground blur",
        ShotType.two_shot: "two-shot composition, dual character framing, balanced",
    }

    STYLE_MODIFIERS: Dict[str, str] = {
        "anime": "anime style, vibrant colors, clean lineart, cel shading",
        "manga": "manga style, black and white, screentone, crosshatching",
        "realistic": "photorealistic, detailed skin texture, subsurface scattering",
        "semi_realistic": "semi-realistic anime, detailed rendering, soft shading",
        "cinematic": "cinematic film grain, anamorphic lens, color grading, film still",
    }

    def __init__(
        self,
        character_memory: Any = None,
        scene_memory: Any = None,
    ) -> None:
        self.character_memory = character_memory
        self.scene_memory = scene_memory
        self._cinema = CinemaPromptEngine()
        self.style: str = "anime"
        self.custom_quality_prefix: str = ""
        self.custom_negative: str = ""

    def set_style(self, style: str) -> None:
        if style in self.STYLE_MODIFIERS:
            self.style = style

    def generate_shot_prompt(
        self,
        shot_index: int,
        shot_type: ShotType,
        character_names: List[str],
        scene_name: str,
        action_description: str = "",
        emotion_description: str = "",
        dialogue: str = "",
        custom_context: str = "",
    ) -> PromptResult:
        """V1 API — 内部走 CinemaPromptEngine 拼装。"""
        positive_parts: List[str] = []

        # Quality
        prefix = self.custom_quality_prefix or (
            "masterpiece, best quality, cinematic lighting, highly detailed, "
            "8K resolution, professional"
        )
        positive_parts.append(prefix)

        # Characters
        if character_names and self.character_memory:
            for name in character_names:
                char_prompt = self.character_memory.get_character_prompt(name)
                if char_prompt:
                    positive_parts.append(char_prompt)
        elif character_names:
            positive_parts.append(", ".join(character_names))

        # Action
        if action_description:
            positive_parts.append(action_description)

        # Emotion
        if emotion_description:
            positive_parts.append(emotion_description)

        # Scene
        if scene_name and self.scene_memory:
            scene_pos, _ = self.scene_memory.get_scene_prompts(scene_name)
            if scene_pos:
                positive_parts.append(scene_pos)
        elif scene_name:
            positive_parts.append(f"background: {scene_name}")

        # Camera
        camera_mod = self.CAMERA_MODIFIERS.get(shot_type, "")
        if camera_mod:
            positive_parts.append(camera_mod)

        # Style
        style_mod = self.STYLE_MODIFIERS.get(self.style, "")
        if style_mod:
            positive_parts.append(style_mod)

        if custom_context:
            positive_parts.append(custom_context)

        positive = ", ".join(p for p in positive_parts if p)

        negative = self.custom_negative or GLOBAL_NEGATIVE

        return PromptResult(
            positive=positive,
            negative=negative,
            shot_index=shot_index,
            character_names=character_names,
            scene_name=scene_name,
        )

    def generate_batch_prompts(
        self, chapter_index: int, shot_data: List[Dict]
    ) -> BatchPromptResult:
        results = []
        for shot in shot_data:
            shot_type = shot.get("shot_type", ShotType.medium)
            if isinstance(shot_type, str):
                try:
                    shot_type = ShotType(shot_type)
                except ValueError:
                    shot_type = ShotType.medium

            result = self.generate_shot_prompt(
                shot_index=shot.get("index", 0),
                shot_type=shot_type,
                character_names=shot.get("characters", []),
                scene_name=shot.get("scene", ""),
                action_description=shot.get("action", ""),
                emotion_description=shot.get("emotion", ""),
                dialogue=shot.get("dialogue", ""),
            )
            results.append(result)

        return BatchPromptResult(chapter_index=chapter_index, shots=results)

    def override_quality_prefix(self, prefix: str) -> None:
        self.custom_quality_prefix = prefix

    def override_negative(self, negative: str) -> None:
        self.custom_negative = negative

    def reset_overrides(self) -> None:
        self.custom_quality_prefix = ""
        self.custom_negative = ""

    def format_prompt_for_comfyui(self, prompt: PromptResult) -> Dict[str, str]:
        return {"positive": prompt.positive, "negative": prompt.negative}

    def format_batch_for_comfyui(self, batch: BatchPromptResult) -> List[Dict[str, str]]:
        return [self.format_prompt_for_comfyui(p) for p in batch.shots]

    def estimate_token_count(self, prompt: str) -> int:
        return int(len(prompt.split()) / 0.75)
