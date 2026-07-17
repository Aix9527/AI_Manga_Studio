"""
AI Manga Studio Pro V4 — Cinema Video Prompt Builder

Director-level video prompt generation integrating:
- Cinematography language (camera movement, framing, lens specs)
- Action choreography (fight sequences, body movement, timing)
- Lighting design (volumetric, rim, practical, color grading)
- Visual effects (speed lines, impact waves, particles, transitions)
- Character motion (micro-expressions, cloth simulation, breath)
- Shot continuity (match cut, dissolve, seamless transitions)

Based on reference materials:
- Wan2.2 studio prompt patterns
- Sora-style storyboard breakdown
- Dynamic comic reverse-engineering
- Latest camera treatment prompts
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


# ============================================================
# Constants & Lookup Tables
# ============================================================

# Emotion → visual effect mapping (anime-style dynamic effects)
EMOTION_VFX_MAP: Dict[str, List[str]] = {
    "angry": ["speed lines radiating from character", "high contrast shadows", "impact wave distortion"],
    "sad": ["soft volumetric light", "rain particle overlay", "desaturated color grade"],
    "happy": ["warm golden hour light", "sparkle particles", "soft bloom glow"],
    "fearful": ["cold blue rim light", "shallow depth of field blur", "vignette darkening"],
    "surprised": ["flashbang white overlay", "radial speed lines", "instant focus pull"],
    "tense": ["high contrast chiaroscuro", "dutch angle tension", "pulse-like breathing motion"],
    "determined": ["sharp rim light edge", "steady camera push", "clean composition"],
    "neutral": ["natural lighting", "subtle ambient motion", "stable framing"],
    "excited": ["dynamic camera orbit", "warm color grade", "fast micro-movements"],
    "calm": ["soft diffused light", "slow pan", "minimal subject motion"],
}

# Shot type → camera movement recommendation
SHOT_CAMERA_MOVEMENT: Dict[str, str] = {
    "close": "slow dolly in, shallow DOF rack focus",
    "medium": "gentle push in with handheld micro-stabilization",
    "wide": "slow crane up revealing environmental context",
    "drone": "smooth aerial orbit around subject",
    "pov": "handheld subtle shake matching walking rhythm",
    "tracking": "lateral tracking shot following subject movement",
    "dutch": "static tilted frame with slow zoom for tension",
    "overhead": "top-down slow descent with 360-degree rotation",
}

# Action type → motion description
ACTION_MOTION_MAP: Dict[str, str] = {
    "walk": "natural walking cycle, arm swing, foot placement",
    "run": "forward lean, rapid stride, hair/cloth trailing",
    "attack": "explosive forward motion, weapon trail, impact frame",
    "defend": "blocking stance, shield raise, defensive posture",
    "sit": "controlled descent, settling motion, relaxed posture",
    "stand": "rising from seated, posture straightening, breathing",
    "gesture": "hand movement toward target, arm extension, pointing",
    "cast_spell": "arm raise with energy gathering, spell circle formation",
    "fight": "dynamic combat sequence, dodge-roll-counter pattern",
    "idle": "subtle breathing, occasional head turn, weight shift",
    "embrace": "arms opening, approaching, gentle contact",
    "bow": "torso forward rotation, hands to sides or clasped",
}

# Lighting presets by time of day
LIGHTING_PRESETS: Dict[str, str] = {
    "dawn": "soft pink-orange gradient sky, volumetric god rays, long cool shadows",
    "morning": "bright directional sunlight, crisp shadows, high visibility",
    "noon": "harsh overhead light, short shadows, high contrast",
    "afternoon": "warm golden angle, long soft shadows, amber tint",
    "dusk": "orange-pink horizon, deep blue fill, cinematic rim light on subjects",
    "night": "moonlight blue wash, practical warm lights, deep shadow pools",
    "rainy": "diffused gray overcast, wet surface reflections, droplet particles",
    "sunny": "clear blue sky, saturated colors, sharp defined shadows",
    "foggy": "low visibility, desaturated midtones, ethereal backlight",
    "stormy": "dark clouds, lightning flashes, wind-driven rain, turbulent motion",
}


# ============================================================
# Data Models
# ============================================================

@dataclass
class ShotCinemaData:
    """Rich cinematic data for a single shot."""
    shot_id: str = ""
    chapter: int = 1
    scene: int = 1
    shot_num: int = 1

    # Camera
    shot_type: str = "medium"          # close/medium/wide/drone/pov/tracking/dutch/overhead
    camera_movement: str = ""          # e.g. "slow dolly in"
    focal_length: str = "50mm"
    aperture: str = "f/2.8"
    depth_of_field: str = "shallow"

    # Subject
    characters: List[str] = field(default_factory=list)
    character_actions: List[str] = field(default_factory=list)
    expressions: List[str] = field(default_factory=list)
    emotion: str = "neutral"

    # Environment
    scene_description: str = ""
    time_of_day: str = "day"
    weather: str = "clear"
    lighting: str = ""

    # Motion
    subject_motion: str = ""
    cloth_motion: str = ""
    micro_expression: str = ""

    # Audio
    dialogue: str = ""
    sfx: str = ""
    bgm_mood: str = ""

    # Effects
    visual_effects: List[str] = field(default_factory=list)
    transition_in: str = "cut"
    transition_out: str = "cut"

    # Continuity
    prev_shot_state: str = ""
    next_shot_setup: str = ""

    # Duration
    duration_sec: float = 5.0


@dataclass
class CinemaVideoPrompt:
    """Structured cinema video prompt for I2V generation."""
    shot_id: str = ""

    # Core description (Chinese, for Wan/Hunyuan video models)
    action_sequence: str = ""          # Time-ordered action description
    camera_motion: str = ""            # Camera movement description
    character_motion: str = ""         # Subject motion description
    expression_motion: str = ""        # Facial micro-expression
    cloth_environment: str = ""        # Wind, particles, environment motion
    lighting_description: str = ""     # Light behavior in the shot

    # English prompt (for models that need it)
    english_prompt: str = ""

    # First frame & last frame descriptions
    first_frame_desc: str = ""
    last_frame_desc: str = ""

    # Negative prompt
    negative_prompt: str = ""

    # Metadata
    motion_strength: float = 0.6       # 0.0-1.0, controls animation intensity
    camera_smooth: bool = True
    fps_target: int = 24
    duration_sec: float = 5.0

    # Full synthesized prompt
    full_prompt: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "action_sequence": self.action_sequence,
            "camera_motion": self.camera_motion,
            "character_motion": self.character_motion,
            "expression_motion": self.expression_motion,
            "cloth_environment": self.cloth_environment,
            "lighting_description": self.lighting_description,
            "english_prompt": self.english_prompt,
            "first_frame_desc": self.first_frame_desc,
            "last_frame_desc": self.last_frame_desc,
            "negative_prompt": self.negative_prompt,
            "motion_strength": self.motion_strength,
            "full_prompt": self.full_prompt,
        }


@dataclass
class ShotTableEntry:
    """Professional shot table entry (镜表)."""
    shot_number: int = 0
    shot_type: str = ""
    camera_angle: str = ""
    camera_movement: str = ""
    subject_action: str = ""
    dialogue: str = ""
    lighting: str = ""
    vfx: str = ""
    duration: float = 0.0
    transition: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "镜号": self.shot_number,
            "景别": self.shot_type,
            "角度": self.camera_angle,
            "运镜": self.camera_movement,
            "画面内容": self.subject_action,
            "台词": self.dialogue,
            "灯光": self.lighting,
            "特效": self.vfx,
            "时长": self.duration,
            "转场": self.transition,
            "备注": self.notes,
        }


# ============================================================
# Cinema Video Prompt Builder
# ============================================================

class CinemaVideoPromptBuilder:
    """Director-level video prompt builder.

    Takes structured ShotCinemaData and produces:
    1. Chinese video prompt (for Wan/Hunyuan models)
    2. English prompt (fallback for models needing English)
    3. First/last frame descriptions (for I2V with reference frames)
    4. Motion parameters (strength, smoothing, FPS)
    5. Professional shot table entry
    """

    # Character name simplification for video prompts
    CHAR_SIMPLIFY = {
        "male": "男人",
        "female": "女人",
        "boy": "少年",
        "girl": "少女",
        "child": "小孩",
        "elderly_man": "老人",
        "elderly_woman": "老妇人",
    }

    def __init__(self, default_style: str = "动漫风格，逼真精细，光影真实，色彩自然"):
        self.default_style = default_style
        self.default_negative = (
            "低质量，模糊，变形，丑陋，多余肢体，水印，文字，签名，"
            "裁剪不当，比例失调，重复角色，面部扭曲，身体碎片"
        )
        logger.info("CinemaVideoPromptBuilder initialized (V4)")

    # ---- Public API ----

    def build(self, shot_data: ShotCinemaData) -> CinemaVideoPrompt:
        """Build a complete cinema video prompt from structured shot data.

        This is the core method that assembles all director-level components.
        """
        prompt = CinemaVideoPrompt(shot_id=shot_data.shot_id)

        # 1. Action sequence (time-ordered)
        prompt.action_sequence = self._build_action_sequence(shot_data)

        # 2. Camera motion
        prompt.camera_motion = self._build_camera_motion(shot_data)

        # 3. Character motion
        prompt.character_motion = self._build_character_motion(shot_data)

        # 4. Expression motion
        prompt.expression_motion = self._build_expression_motion(shot_data)

        # 5. Cloth & environment motion
        prompt.cloth_environment = self._build_cloth_environment(shot_data)

        # 6. Lighting description
        prompt.lighting_description = self._build_lighting(shot_data)

        # 7. First/last frame descriptions
        prompt.first_frame_desc = self._build_first_frame(shot_data)
        prompt.last_frame_desc = self._build_last_frame(shot_data)

        # 8. Motion parameters
        prompt.motion_strength = self._infer_motion_strength(shot_data)
        prompt.duration_sec = shot_data.duration_sec

        # 9. English prompt
        prompt.english_prompt = self._translate_to_english(prompt)

        # 10. Negative prompt
        prompt.negative_prompt = self.default_negative

        # 11. Synthesize full prompt
        prompt.full_prompt = self._synthesize_full(prompt)

        logger.debug(
            f"CinemaVideoPromptBuilder: built prompt for {shot_data.shot_id}, "
            f"motion_strength={prompt.motion_strength:.2f}"
        )
        return prompt

    def build_batch(self, shots: List[ShotCinemaData]) -> List[CinemaVideoPrompt]:
        """Build video prompts for a batch of shots."""
        prompts = []
        for shot in shots:
            prompts.append(self.build(shot))
        logger.info(f"CinemaVideoPromptBuilder: built {len(prompts)} video prompts")
        return prompts

    def build_shot_table(self, prompts: List[CinemaVideoPrompt], shots: List[ShotCinemaData]) -> List[ShotTableEntry]:
        """Build a professional shot table (镜表) from prompts."""
        table = []
        for i, (p, s) in enumerate(zip(prompts, shots)):
            entry = ShotTableEntry(
                shot_number=s.shot_num,
                shot_type=s.shot_type,
                camera_angle=self._infer_camera_angle(s),
                camera_movement=p.camera_motion,
                subject_action=p.action_sequence,
                dialogue=s.dialogue,
                lighting=p.lighting_description,
                vfx=", ".join(s.visual_effects) if s.visual_effects else "",
                duration=s.duration_sec,
                transition=s.transition_out,
                notes=s.scene_description,
            )
            table.append(entry)
        return table

    # ---- Internal Builders ----

    def _build_action_sequence(self, shot: ShotCinemaData) -> str:
        """Build time-ordered action sequence for the shot."""
        parts = []

        # 0-0.15s discard frame note
        parts.append("0秒-0.15秒为固定废帧")

        # Character action from motion map
        for action in shot.character_actions:
            mapped = ACTION_MOTION_MAP.get(action.lower(), action)
            parts.append(mapped)

        # If no mapped action, use direct description
        if not shot.character_actions and shot.subject_motion:
            parts.append(shot.subject_motion)

        # SFX integration
        if shot.sfx:
            parts.append(shot.sfx)

        # Dialogue timing
        if shot.dialogue:
            char_count = len(shot.dialogue)
            duration = max(1.5, char_count / 3.0)
            parts.append(f"对话时间戳: {shot.dialogue} (约{duration:.1f}秒)")

        # Scene action
        if shot.scene_description:
            parts.append(f"场景中: {shot.scene_description}")

        return "。".join(parts[:5]) + "。" if parts else "角色保持静止"

    def _build_camera_motion(self, shot: ShotCinemaData) -> str:
        """Build camera movement description."""
        # Use explicit camera_movement if provided
        if shot.camera_movement:
            base = shot.camera_movement
        else:
            # Infer from shot type
            base = SHOT_CAMERA_MOVEMENT.get(shot.shot_type, "slow push in")

        # Add lens specs
        lens_info = f"{shot.focal_length}, {shot.aperture}"
        dof_note = f"{'浅景深' if shot.depth_of_field == 'shallow' else '深景深'}"

        return f"镜头{base}，{lens_info}，{dof_note}"

    def _build_character_motion(self, shot: ShotCinemaData) -> str:
        """Build subject motion description."""
        parts = []

        if shot.character_actions:
            for action in shot.character_actions:
                mapped = ACTION_MOTION_MAP.get(action.lower(), action)
                parts.append(mapped)

        if shot.cloth_motion:
            parts.append(shot.cloth_motion)

        if not parts:
            parts.append("角色保持静止")

        return "、".join(parts)

    def _build_expression_motion(self, shot: ShotCinemaData) -> str:
        """Build facial micro-expression description."""
        parts = []

        if shot.expressions:
            parts.extend(shot.expressions)
        elif shot.micro_expression:
            parts.append(shot.micro_expression)
        else:
            # Emotion-based default expression
            expr_map = {
                "angry": "眉头紧锁，眼神锐利，嘴角下沉",
                "sad": "眼神低垂，微微皱眉，嘴唇紧闭",
                "happy": "嘴角上扬，眼睛微弯，自然微笑",
                "fearful": "眼睛睁大，瞳孔收缩，呼吸急促",
                "surprised": "眉毛上扬，眼睛睁大，嘴巴微张",
                "tense": "咬紧牙关，颈部肌肉紧绷",
                "determined": "目光坚定，下巴微抬，表情沉稳",
                "neutral": "自然表情，轻微眨眼",
            }
            parts.append(expr_map.get(shot.emotion, "自然表情，轻微眨眼"))

        return "，".join(parts)

    def _build_cloth_environment(self, shot: ShotCinemaData) -> str:
        """Build cloth and environmental motion."""
        parts = []

        # Weather-based environment
        weather_env = {
            "rain": "雨水滴落，地面水花飞溅，衣物湿润贴身",
            "snow": "雪花飘落，地面覆盖积雪，呼出白气",
            "wind": "风吹动头发和衣物，树叶摇曳",
            "fog": "雾气流动，能见度降低，背景模糊",
            "storm": "狂风暴雨，树木剧烈摇晃，闪电照亮天空",
        }
        w = shot.weather.lower() if shot.weather else ""
        if w in weather_env:
            parts.append(weather_env[w])

        # Explicit cloth motion
        if shot.cloth_motion:
            parts.append(shot.cloth_motion)

        # VFX particles
        for vfx in shot.visual_effects:
            parts.append(vfx)

        return "；".join(parts) if parts else "静态环境，无明显风效"

    def _build_lighting(self, shot: ShotCinemaData) -> str:
        """Build lighting description."""
        if shot.lighting:
            return shot.lighting

        # Infer from time of day
        tod = shot.time_of_day.lower() if shot.time_of_day else "day"
        preset = LIGHTING_PRESETS.get(tod, LIGHTING_PRESETS["sunny"])
        return preset

    def _build_first_frame(self, shot: ShotCinemaData) -> str:
        """Describe the first frame state for I2V reference."""
        parts = []

        # Characters in initial state
        if shot.characters:
            chars = "、".join(shot.characters)
            parts.append(f"画面主体: {chars}")

        # Initial pose
        if shot.character_actions:
            parts.append(f"初始姿态: {ACTION_MOTION_MAP.get(shot.character_actions[0].lower(), shot.character_actions[0])}")

        # Scene context
        if shot.scene_description:
            parts.append(f"场景: {shot.scene_description}")

        # Lighting
        parts.append(f"灯光: {self._build_lighting(shot)}")

        return "。".join(parts)

    def _build_last_frame(self, shot: ShotCinemaData) -> str:
        """Describe the last frame state for I2V reference."""
        parts = []

        # End state of action
        if shot.character_actions:
            action = shot.character_actions[-1]
            parts.append(f"结束姿态: {ACTION_MOTION_MAP.get(action.lower(), action)}")

        # Camera end position
        parts.append(f"镜头最终位置: {shot.camera_movement or '推近至主体'}")

        # Lighting at end
        parts.append(f"灯光变化: {self._build_lighting(shot)}")

        return "。".join(parts) if parts else "画面结束状态"

    def _infer_motion_strength(self, shot: ShotCinemaData) -> float:
        """Infer motion strength based on shot content."""
        base = 0.5  # default

        # Boost for action shots
        action_keywords = ["attack", "fight", "run", "jump", "cast_spell"]
        for action in shot.character_actions:
            if action.lower() in action_keywords:
                base = max(base, 0.8)
                break

        # Reduce for dialogue/static shots
        if shot.emotion in ("calm", "neutral") and not shot.character_actions:
            base = min(base, 0.3)

        # Weather boosts
        if shot.weather and shot.weather.lower() in ("storm", "rain"):
            base = min(base + 0.1, 0.9)

        return round(base, 2)

    def _infer_camera_angle(self, shot: ShotCinemaData) -> str:
        """Infer camera angle from shot type."""
        angle_map = {
            "close": "近景平视",
            "medium": "中景平视",
            "wide": "全景平视",
            "drone": "航拍俯视",
            "pov": "主观视角",
            "tracking": "跟拍侧视",
            "dutch": "荷兰角倾斜",
            "overhead": "顶视俯拍",
        }
        return angle_map.get(shot.shot_type, "中景平视")

    def _translate_to_english(self, prompt: CinemaVideoPrompt) -> str:
        """Generate English version of the video prompt.

        Simplified translation for models that need English prompts.
        """
        parts = []

        if prompt.action_sequence:
            # Strip Chinese-specific markers
            en_action = prompt.action_sequence.replace("0秒-0.15秒为固定废帧", "")
            en_action = re.sub(r"对话时间戳.*$", "", en_action).strip()
            if en_action:
                parts.append(f"Action: {en_action}")

        if prompt.camera_motion:
            parts.append(f"Camera: {prompt.camera_motion}")

        if prompt.character_motion:
            parts.append(f"Subject motion: {prompt.character_motion}")

        if prompt.expression_motion:
            parts.append(f"Expression: {prompt.expression_motion}")

        if prompt.cloth_environment:
            parts.append(f"Environment: {prompt.cloth_environment}")

        if prompt.lighting_description:
            parts.append(f"Lighting: {prompt.lighting_description}")

        parts.append(self.default_style)

        return "; ".join(parts) if parts else "character animation with camera movement"

    def _synthesize_full(self, prompt: CinemaVideoPrompt) -> str:
        """Combine all fields into a complete prompt string."""
        sections = [
            ("画面描述", prompt.action_sequence),
            ("镜头运动", prompt.camera_motion),
            ("角色动作", prompt.character_motion),
            ("表情变化", prompt.expression_motion),
            ("环境特效", prompt.cloth_environment),
            ("灯光效果", prompt.lighting_description),
        ]

        lines = []
        for label, content in sections:
            if content:
                lines.append(f"# {label}\n{content}")

        return "\n\n".join(lines)

    def build_from_shot_dict(self, shot_dict: Dict[str, Any]) -> CinemaVideoPrompt:
        """Build from a raw shot dictionary (convenience wrapper)."""
        # Convert dict to ShotCinemaData
        data = ShotCinemaData(
            shot_id=shot_dict.get("shot_id", ""),
            chapter=shot_dict.get("chapter", 1),
            scene=shot_dict.get("scene", 1),
            shot_num=shot_dict.get("shot", 1),
            shot_type=shot_dict.get("shot_type", "medium"),
            camera_movement=shot_dict.get("camera_movement", ""),
            focal_length=shot_dict.get("focal_length", "50mm"),
            aperture=shot_dict.get("aperture", "f/2.8"),
            depth_of_field=shot_dict.get("depth_of_field", "shallow"),
            characters=shot_dict.get("characters", []),
            character_actions=shot_dict.get("character_actions", []),
            expressions=shot_dict.get("expressions", []),
            emotion=shot_dict.get("emotion", "neutral"),
            scene_description=shot_dict.get("scene_description", ""),
            time_of_day=shot_dict.get("time_of_day", "day"),
            weather=shot_dict.get("weather", "clear"),
            lighting=shot_dict.get("lighting", ""),
            subject_motion=shot_dict.get("subject_motion", ""),
            cloth_motion=shot_dict.get("cloth_motion", ""),
            micro_expression=shot_dict.get("micro_expression", ""),
            dialogue=shot_dict.get("dialogue", ""),
            sfx=shot_dict.get("sfx", ""),
            bgm_mood=shot_dict.get("bgm_mood", ""),
            visual_effects=shot_dict.get("visual_effects", []),
            transition_in=shot_dict.get("transition_in", "cut"),
            transition_out=shot_dict.get("transition_out", "cut"),
            duration_sec=shot_dict.get("duration_sec", 5.0),
        )
        return self.build(data)
