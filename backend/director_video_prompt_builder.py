"""
AI Manga Studio Pro V5 — Director-Level Video Prompt Builder

Generates cinematic video prompts with:
- Director thinking (story intent, emotional arc, pacing)
- Camera language (movement, lens, angle, framing)
- Cinematography (lighting design, color grading, atmosphere)
- Choreography (fight sequences, body movement, timing)
- Visual effects (particles, speed lines, impact waves, transitions)
- Shot continuity (match cuts, dissolve, seamless transitions)
- First/last frame descriptions for Wan2.2 I2V

Based on:
- Wan2.2 studio prompt patterns (wan工作室爆量)
- Sora-style storyboard breakdown
- Dynamic comic reverse-engineering
- Latest camera treatment prompts
- Professional shot table (镜表) format
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


# ============================================================
# Cinematic Lookup Tables
# ============================================================

CAMERA_MOVEMENTS = {
    # Push/Pull
    "push_in": {
        "cn": "镜头缓慢推进，焦点逐渐收紧于主体面部",
        "en": "slow camera push-in, focus tightening on subject face",
    },
    "pull_out": {
        "cn": "镜头缓慢拉远，展现环境与主体的关系",
        "en": "slow camera pull-out, revealing environment-subject relationship",
    },
    "dolly_in": {
        "cn": "轨道前推，平滑靠近主体，浅景深虚化背景",
        "en": "dolly in, smooth approach toward subject, shallow DOF blurs background",
    },
    "dolly_out": {
        "cn": "轨道后拉，视野逐渐开阔",
        "en": "dolly out, field of view gradually widens",
    },
    # Tracking
    "track_left": {
        "cn": "横移镜头跟随主体向左移动",
        "en": "tracking shot following subject moving left",
    },
    "track_right": {
        "cn": "横移镜头跟随主体向右移动",
        "en": "tracking shot following subject moving right",
    },
    "orbit": {
        "cn": "环绕拍摄，镜头绕主体360度旋转",
        "en": "orbit shot, camera circles subject 360 degrees",
    },
    # Crane/Boom
    "crane_up": {
        "cn": "摇臂上升，从近景逐渐升至全景俯瞰",
        "en": "crane up, rising from close-up to全景 aerial view",
    },
    "crane_down": {
        "cn": "摇臂下降，从全景缓缓降至特写",
        "en": "crane down, descending from wide to close-up",
    },
    # Handheld
    "handheld": {
        "cn": "手持摄影，轻微呼吸晃动，增强临场感",
        "en": "handheld camera, subtle breathing shake, enhancing presence",
    },
    "handheld_shake": {
        "cn": "手持剧烈晃动，表现紧张冲突场面",
        "en": "intense handheld shake, conveying tension and conflict",
    },
    # Static
    "static": {
        "cn": "固定镜头，画面稳定不动",
        "en": "static locked-off shot, camera completely still",
    },
    "slow_zoom": {
        "cn": "缓慢变焦推进，营造压迫感或专注感",
        "en": "slow zoom in, creating pressure or concentration",
    },
    "rack_focus": {
        "cn": "焦点转换，从前景区切换到背景区",
        "en": "rack focus, shifting focus from foreground to background",
    },
    # Special
    "whip_pan": {
        "cn": "快速甩镜头，制造冲击转折效果",
        "en": "whip pan, fast directional blur for dramatic transition",
    },
    "tilt_up": {
        "cn": "仰拍倾斜，镜头从下往上扫过主体",
        "en": "tilt up, camera tilting upward along subject",
    },
    "tilt_down": {
        "cn": "俯拍倾斜，镜头从上往下扫过主体",
        "en": "tilt down, camera tilting downward along subject",
    },
    "steadicam": {
        "cn": "稳定器跟拍，流畅穿梭于场景之间",
        "en": "steadicam tracking, fluid movement through the scene",
    },
}

LIGHTING_PRESETS = {
    "dawn": {
        "cn": "黎明柔光，粉橙色渐变天空，体积光穿透薄雾，长冷色阴影",
        "en": "dawn soft light, pink-orange gradient sky, volumetric god rays through mist, long cool shadows",
    },
    "morning": {
        "cn": "明亮晨光，阳光从左上方照射，清晰锐利阴影",
        "en": "bright morning light, sunlight from upper-left, crisp sharp shadows",
    },
    "noon": {
        "cn": "正午顶光，强烈直射，短阴影，高对比度",
        "en": "harsh overhead noon light, strong direct beam, short shadows, high contrast",
    },
    "afternoon": {
        "cn": "午后暖光，金色斜射，柔和长影，琥珀色调",
        "en": "warm afternoon golden hour light, oblique rays, soft long shadows, amber tint",
    },
    "dusk": {
        "cn": "黄昏电影光，橙粉色地平线光源，深蓝补光，角色边缘轮廓光",
        "en": "dusk cinematic light, orange-pink horizon key, deep blue fill, rim light on subject edges",
    },
    "night": {
        "cn": "月光蓝色洗刷，暖色实用光源点缀，深阴影池，远处路灯柔轮廓光",
        "en": "moonlight blue wash, warm practical accent lights, deep shadow pools, soft rim from distant lamp",
    },
    "rainy": {
        "cn": "阴天散射灰光，无直射阴影，湿面反射，雨滴高光",
        "en": "overcast diffused gray light, no direct shadows, wet surface reflections, raindrop highlights",
    },
    "stormy": {
        "cn": "乌云压顶，闪电间歇照亮，狂风暴雨，湍流动感",
        "en": "dark storm clouds, intermittent lightning illumination, violent wind and rain, turbulent motion",
    },
    "foggy": {
        "cn": "低能见度，饱和中调降低，逆光朦胧感，雾气流动",
        "en": "low visibility, desaturated midtones, ethereal backlight, flowing fog",
    },
    "studio": {
        "cn": "三点布光，主光45度，补光对面，轮廓光后方，干净背景",
        "en": "three-point studio lighting, key at 45 degrees, fill opposite, rim behind, clean background",
    },
    "neon": {
        "cn": "霓虹冷光，赛博朋克色调，紫色蓝色交替闪烁",
        "en": "neon cold light, cyberpunk color grade, alternating purple and blue flicker",
    },
    "candlelight": {
        "cn": "烛光暖光，摇曳不定，深暖色调，周围暗部",
        "en": "candlelight warm glow, flickering, deep warm tones, dark surroundings",
    },
}

EMOTION_VFX_MAP = {
    "angry": {
        "cn": "速度线从角色四周辐射，高对比度阴影，冲击波扭曲效果",
        "en": "speed lines radiating from character, high contrast shadows, impact wave distortion",
    },
    "sad": {
        "cn": "柔和体积光，雨粒子叠加，褪色色彩分级",
        "en": "soft volumetric light, rain particle overlay, desaturated color grade",
    },
    "happy": {
        "cn": "温暖金色时刻光照， sparkle粒子，柔光辉晕",
        "en": "warm golden hour light, sparkle particles, soft bloom glow",
    },
    "fearful": {
        "cn": "冷蓝轮廓光，浅景深模糊，暗角加重",
        "en": "cold blue rim light, shallow DOF blur, vignette darkening",
    },
    "surprised": {
        "cn": "闪光白叠加，径向速度线，瞬间焦点转换",
        "en": "flashbang white overlay, radial speed lines, instant focus pull",
    },
    "tense": {
        "cn": "高对比明暗对照法，荷兰角张力构图，脉冲式呼吸运动",
        "en": "high contrast chiaroscuro, dutch angle tension, pulse-like breathing motion",
    },
    "determined": {
        "cn": "锋利轮廓光边缘，稳定镜头推进，干净构图",
        "en": "sharp rim light edge, steady camera push, clean composition",
    },
    "neutral": {
        "cn": "自然光照，微妙环境运动，稳定构图",
        "en": "natural lighting, subtle ambient motion, stable framing",
    },
    "excited": {
        "cn": "动态镜头环绕，暖色色彩分级，快速微运动",
        "en": "dynamic camera orbit, warm color grade, fast micro-movements",
    },
    "calm": {
        "cn": "柔和散射光，慢速平移，最小主体运动",
        "en": "soft diffused light, slow pan, minimal subject motion",
    },
}

ACTION_MOTION_MAP = {
    "walk": "自然行走循环，手臂摆动，步伐稳健",
    "run": "身体前倾，大步奔跑，头发衣物向后飘动",
    "attack": "爆发性前冲动作，武器轨迹，命中帧",
    "defend": "防御姿态，举盾格挡，后退半步",
    "sit": "受控下落动作，坐下，放松姿态",
    "stand": "从坐姿起身，站直，整理衣物",
    "gesture": "手部指向目标，手臂伸展",
    "cast_spell": "手臂抬起聚集能量，魔法阵形成",
    "fight": "动态战斗序列，闪避-反击模式",
    "idle": "微妙呼吸起伏，偶尔转头，重心微调",
    "embrace": "双臂张开，靠近，轻柔接触",
    "bow": "上半身前倾弯曲，双手放两侧或交叠",
    "draw_weapon": "手伸向武器，拔刀/取枪动作",
    "fall": "失去平衡，向后倒下的物理运动",
    "jump": "屈膝蓄力，腾空跃起，落地缓冲",
}

SHOT_TYPE_CAMERAS = {
    "close": "85mm人像镜头，f/1.8浅景深，背景完全虚化",
    "medium": "50mm标准镜头，f/2.8中等景深，保留上半身与环境关系",
    "wide": "24mm广角镜头，f/8深景深，完整环境构图",
    "drone": "16mm超广角航拍，f/11最大景深",
    "pov": "24mm广角主观视角，f/2.0轻微桶形畸变增强沉浸感",
    "tracking": "35mm镜头，f/4中等景深，运动模糊",
    "dutch": "35mm镜头，f/2.8倾斜15度，戏剧张力",
    "overhead": "50mm镜头，f/5.6顶部平面构图",
    "extreme_close": "135mm超长焦，f/1.4极浅景深，仅眼部或局部特写",
    "two_shot": "35mm镜头，f/4，双人构图，中间对焦",
    "over_shoulder": "50mm镜头，f/2.8，过肩视角，前景虚化",
}


# ============================================================
# Data Models
# ============================================================

@dataclass
class DirectorNote:
    """A single director's note for the shot."""
    category: str = ""          # story, pacing, emotion, camera, lighting, vfx, sound
    content: str = ""
    priority: str = "normal"    # high, normal, low


@dataclass
class CinematicShot:
    """Complete cinematic description for a single shot."""
    shot_id: str = ""
    chapter: int = 1
    scene: int = 1
    shot_num: int = 1

    # Director-level
    director_intent: str = ""       # What this shot achieves narratively
    emotional_arc: str = ""         # Emotion progression through the shot
    pacing: str = "normal"          # fast / normal / slow
    transition_in: str = "cut"      # cut / fade / dissolve / whip / match
    transition_out: str = "cut"

    # Camera
    shot_type: str = "medium"       # close/medium/wide/drone/pov/tracking/dutch/overhead
    camera_movement: str = ""       # key from CAMERA_MOVEMENTS
    focal_length: str = ""
    aperture: str = "f/2.8"
    depth_of_field: str = "shallow"
    angle: str = "eye_level"        # eye_level / low_angle / high_angle / Dutch

    # Subject
    characters: List[str] = field(default_factory=list)
    character_actions: List[str] = field(default_factory=list)
    expressions: List[str] = field(default_factory=list)
    emotion: str = "neutral"

    # Environment
    scene_description: str = ""
    time_of_day: str = "day"
    weather: str = "clear"
    custom_lighting: str = ""

    # Motion
    subject_motion: str = ""
    cloth_motion: str = ""
    micro_expression: str = ""

    # Effects
    visual_effects: List[str] = field(default_factory=list)

    # Audio
    dialogue: str = ""
    sfx: str = ""
    bgm_mood: str = ""

    # Timing
    duration_sec: float = 5.0

    # Continuity
    prev_shot_state: str = ""
    next_shot_setup: str = ""


@dataclass
class DirectorVideoPrompt:
    """Structured video prompt with director-level thinking."""
    shot_id: str = ""

    # Core Chinese prompt for Wan/Hunyuan
    action_sequence: str = ""
    camera_motion: str = ""
    character_motion: str = ""
    expression_motion: str = ""
    cloth_environment: str = ""
    lighting_description: str = ""
    vfx_description: str = ""
    sound_design: str = ""

    # Director's thinking
    director_note: str = ""
    story_intent: str = ""
    emotional_progression: str = ""
    pacing_note: str = ""

    # Frame descriptions
    first_frame_desc: str = ""
    last_frame_desc: str = ""

    # English prompt (for models needing it)
    english_prompt: str = ""

    # Parameters
    motion_strength: float = 0.6
    camera_smooth: bool = True
    fps_target: int = 24
    duration_sec: float = 5.0

    # Negative prompt
    negative_prompt: str = ""

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
            "vfx_description": self.vfx_description,
            "sound_design": self.sound_design,
            "director_note": self.director_note,
            "story_intent": self.story_intent,
            "emotional_progression": self.emotional_progression,
            "pacing_note": self.pacing_note,
            "first_frame_desc": self.first_frame_desc,
            "last_frame_desc": self.last_frame_desc,
            "english_prompt": self.english_prompt,
            "motion_strength": self.motion_strength,
            "fps_target": self.fps_target,
            "duration_sec": self.duration_sec,
            "negative_prompt": self.negative_prompt,
            "full_prompt": self.full_prompt,
        }


@dataclass
class ShotTableEntry:
    """Professional shot table (镜表) entry."""
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
    emotional_note: str = ""
    director_note: str = ""

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
            "情绪备注": self.emotional_note,
            "导演备注": self.director_note,
        }


# ============================================================
# Director Video Prompt Builder
# ============================================================

class DirectorVideoPromptBuilder:
    """Director-level video prompt builder for cinematic I2V generation.

    Produces:
    1. Structured Chinese video prompt (for Wan2.2 / Hunyuan)
    2. Director's thinking notes (story intent, pacing, emotion)
    3. First/last frame descriptions for I2V keyframing
    4. Professional shot table (镜表)
    5. English fallback prompt
    6. Motion parameters (strength, smoothing, FPS)
    """

    DEFAULT_VIDEO_STYLE = "动漫风格，逼真精细，光影真实，色彩自然，透视准确，质感丰富，构图严谨，细节丰富"
    DEFAULT_NEGATIVE = (
        "低质量，模糊，变形，丑陋，多余肢体，水印，文字，签名，"
        "裁剪不当，比例失调，重复角色，面部扭曲，身体碎片，抖动，闪烁，变形"
    )

    def __init__(self, style: str = ""):
        self.style = style or self.DEFAULT_VIDEO_STYLE
        self.negative = self.DEFAULT_NEGATIVE
        logger.info("DirectorVideoPromptBuilder initialized (V5)")

    # ---- Public API ----

    def build_from_shot(
        self,
        shot: CinematicShot,
        prev_shot: Optional[CinematicShot] = None,
        next_shot: Optional[CinematicShot] = None,
    ) -> DirectorVideoPrompt:
        """Build a complete director-level video prompt from a CinematicShot.

        This is the core method that assembles all cinematic components.
        """
        prompt = DirectorVideoPrompt(shot_id=shot.shot_id)

        # 1. Director's thinking
        prompt.director_note = self._build_director_note(shot, prev_shot, next_shot)
        prompt.story_intent = self._build_story_intent(shot)
        prompt.emotional_progression = self._build_emotional_arc(shot)
        prompt.pacing_note = self._build_pacing_note(shot)

        # 2. Action sequence (time-ordered)
        prompt.action_sequence = self._build_action_sequence(shot)

        # 3. Camera motion
        prompt.camera_motion = self._build_camera_motion(shot, prev_shot, next_shot)

        # 4. Character motion
        prompt.character_motion = self._build_character_motion(shot)

        # 5. Expression motion
        prompt.expression_motion = self._build_expression_motion(shot)

        # 6. Cloth & environment motion
        prompt.cloth_environment = self._build_cloth_environment(shot)

        # 7. Lighting description
        prompt.lighting_description = self._build_lighting(shot)

        # 8. VFX description
        prompt.vfx_description = self._build_vfx(shot)

        # 9. Sound design note
        prompt.sound_design = self._build_sound_design(shot)

        # 10. First/last frame descriptions
        prompt.first_frame_desc = self._build_first_frame(shot, prev_shot)
        prompt.last_frame_desc = self._build_last_frame(shot, next_shot)

        # 11. Motion parameters
        prompt.motion_strength = self._infer_motion_strength(shot)
        prompt.duration_sec = shot.duration_sec
        prompt.fps_target = shot.duration_sec > 0 and int(24 * shot.duration_sec) or 120

        # 12. English prompt
        prompt.english_prompt = self._build_english_prompt(prompt, shot)

        # 13. Negative prompt
        prompt.negative_prompt = self.negative

        # 14. Synthesize full prompt
        prompt.full_prompt = self._synthesize_full(prompt, shot)

        logger.debug(
            f"DirectorVideoPromptBuilder: built prompt for {shot.shot_id}, "
            f"motion_strength={prompt.motion_strength:.2f}"
        )
        return prompt

    def build_batch(
        self,
        shots: List[CinematicShot],
    ) -> List[DirectorVideoPrompt]:
        """Build director-level prompts for a sequence of shots."""
        prompts = []
        for i, shot in enumerate(shots):
            prev = shots[i - 1] if i > 0 else None
            nxt = shots[i + 1] if i < len(shots) - 1 else None
            prompts.append(self.build_from_shot(shot, prev, nxt))
        logger.info(f"DirectorVideoPromptBuilder: built {len(prompts)} director prompts")
        return prompts

    def build_shot_table(
        self,
        prompts: List[DirectorVideoPrompt],
        shots: List[CinematicShot],
    ) -> List[ShotTableEntry]:
        """Build a professional shot table (镜表) from prompts."""
        table = []
        for p, s in zip(prompts, shots):
            entry = ShotTableEntry(
                shot_number=s.shot_num,
                shot_type=s.shot_type,
                camera_angle=self._infer_camera_angle(s),
                camera_movement=p.camera_motion,
                subject_action=p.action_sequence,
                dialogue=s.dialogue,
                lighting=p.lighting_description,
                vfx=p.vfx_description,
                duration=s.duration_sec,
                transition=s.transition_out,
                emotional_note=p.emotional_progression,
                director_note=p.director_note,
            )
            table.append(entry)
        return table

    # ---- Internal: Director Thinking ----

    def _build_director_note(
        self,
        shot: CinematicShot,
        prev: Optional[CinematicShot],
        nxt: Optional[CinematicShot],
    ) -> str:
        """Build director's thinking note for this shot."""
        notes = []

        # Story function
        story_funcs = {
            "close": "建立角色情感连接的特写镜头",
            "medium": "展示角色动作与表情的主镜头",
            "wide": "交代环境与空间关系的全景镜头",
            "drone": "宏观叙事的空间展示镜头",
            "pov": "观众代入的主观视角镜头",
            "tracking": "跟随主体运动的动态镜头",
            "dutch": "制造不安与张力的倾斜镜头",
            "overhead": "上帝视角的俯视镜头",
            "two_shot": "双人关系的对话镜头",
            "over_shoulder": "对话中的过肩视角镜头",
        }
        func = story_funcs.get(shot.shot_type, "叙事镜头")
        notes.append(f"本镜头功能：{func}")

        # Continuity
        if prev and shot.transition_in != "cut":
            notes.append(f"与前镜头{prev.shot_id}采用{shot.transition_in}转场衔接")
        if nxt and shot.transition_out != "cut":
            notes.append(f"与后镜头{nxt.shot_id}采用{shot.transition_out}转场分离")

        # Emotional intent
        emotion_intents = {
            "angry": "愤怒爆发的情绪高点",
            "sad": "悲伤沉淀的情感低谷",
            "happy": "愉悦释放的情绪高点",
            "fearful": "恐惧压迫的情感低谷",
            "surprised": "意外转折的情绪爆发",
            "tense": "紧张积累的情绪铺垫",
            "determined": "坚定决断的情绪节点",
            "excited": "兴奋高涨的情绪推进",
            "calm": "平静过渡的情绪缓冲",
            "neutral": "中性叙述的情绪平稳段",
        }
        ei = emotion_intents.get(shot.emotion, "情绪平稳")
        notes.append(f"情绪定位：{ei}")

        return "；".join(notes)

    def _build_story_intent(self, shot: CinematicShot) -> str:
        """What narrative purpose does this shot serve?"""
        intents = {
            "close": "聚焦角色内心情感，让观众看到细微表情变化",
            "medium": "展示角色动作与环境的互动关系",
            "wide": "建立场景空间感，交代人物所处环境",
            "drone": "宏观展示场景全貌，建立空间方位",
            "pov": "让观众代入角色视角，体验角色感受",
            "tracking": "跟随角色运动，保持视觉连续性",
            "dutch": "打破平衡，制造不安与紧张感",
            "overhead": "上帝视角俯瞰，展示全局态势",
            "two_shot": "展现两人之间的互动与关系",
            "over_shoulder": "对话中的主观视角，增强代入感",
        }
        base = intents.get(shot.shot_type, "叙事推进")

        if shot.character_actions:
            action = shot.character_actions[0]
            mapped = ACTION_MOTION_MAP.get(action.lower(), action)
            base += f"，角色执行{mapped}"

        return base

    def _build_emotional_arc(self, shot: CinematicShot) -> str:
        """Emotional progression through the shot duration."""
        if not shot.emotion or shot.emotion == "neutral":
            return "情绪平稳过渡"

        # Emotion-based emotional arc
        arcs = {
            "angry": "从隐忍到爆发的情绪递进",
            "sad": "从平静到悲伤的情绪下沉",
            "happy": "从期待到喜悦的情绪上扬",
            "fearful": "从警觉到恐惧的情绪攀升",
            "surprised": "从平静到震惊的瞬间爆发",
            "tense": "紧张感持续累积",
            "determined": "犹豫到坚定的情绪转折",
            "excited": "兴奋感逐步升级",
            "calm": "从波动回归平静的舒缓过程",
        }
        return arcs.get(shot.emotion, f"{shot.emotion}情绪表达")

    def _build_pacing_note(self, shot: CinematicShot) -> str:
        """Pacing instruction for the shot."""
        duration = shot.duration_sec
        action_count = len(shot.character_actions)

        if duration <= 2.0:
            return "短镜头快节奏，干净利落"
        elif duration >= 8.0:
            return "长镜头慢节奏，充分展开情绪"
        elif action_count >= 2:
            return "中等节奏，包含多个动作段落"
        else:
            return "正常节奏，平稳推进"

    # ---- Internal: Action Sequence ----

    def _build_action_sequence(self, shot: CinematicShot) -> str:
        """Build time-ordered action sequence for the shot."""
        parts = []

        # 0-0.15s discard frame note
        parts.append("0秒-0.15秒为固定废帧")

        # Character action with motion map
        for action in shot.character_actions:
            mapped = ACTION_MOTION_MAP.get(action.lower(), action)
            parts.append(mapped)

        # If no mapped action, use direct description
        if not shot.character_actions and shot.subject_motion:
            parts.append(shot.subject_motion)

        # Dialogue timing
        if shot.dialogue:
            char_count = len(shot.dialogue)
            duration = max(1.5, char_count / 3.0)
            parts.append(f"对话时间戳：{shot.dialogue}（约{duration:.1f}秒）")

        # Scene action
        if shot.scene_description:
            parts.append(f"场景中：{shot.scene_description}")

        # SFX
        if shot.sfx:
            parts.append(f"音效：{shot.sfx}")

        result = "。".join(parts[:6]) + "。" if parts else "角色保持静止"
        return result

    # ---- Internal: Camera Motion ----

    def _build_camera_motion(
        self,
        shot: CinematicShot,
        prev: Optional[CinematicShot],
        nxt: Optional[CinematicShot],
    ) -> str:
        """Build camera movement description."""
        parts = []

        # Camera movement from lookup
        if shot.camera_movement:
            cam_data = CAMERA_MOVEMENTS.get(shot.camera_movement)
            if cam_data:
                parts.append(cam_data["cn"])
            else:
                parts.append(shot.camera_movement)
        else:
            # Infer from shot type
            default_movements = {
                "close": "缓慢推进，焦点收紧于面部",
                "medium": "轻微前推配合手持微稳",
                "wide": "缓慢摇臂上升展现环境全貌",
                "drone": "平滑空中环绕主体",
                "pov": "手持微晃匹配步行节奏",
                "tracking": "横向跟随镜头",
                "dutch": "静态倾斜构图配合缓慢缩放",
                "overhead": "顶部缓慢下降360度旋转",
                "two_shot": "固定双人构图，轻微呼吸晃动",
                "over_shoulder": "过肩固定镜头，焦点在对话者",
            }
            parts.append(default_movements.get(shot.shot_type, "缓慢推进"))

        # Lens specs
        if shot.focal_length:
            parts.append(f"{shot.focal_length}焦距")
        elif shot.shot_type in SHOT_TYPE_CAMERAS:
            parts.append(SHOT_TYPE_CAMERAS[shot.shot_type])

        # Angle
        angle_map = {
            "eye_level": "平视",
            "low_angle": "低角度仰视",
            "high_angle": "高角度俯视",
            "dutch": "荷兰角倾斜",
        }
        angle = angle_map.get(shot.angle, shot.angle)
        if angle != "eye_level":
            parts.append(angle)

        return "，".join(parts)

    # ---- Internal: Character Motion ----

    def _build_character_motion(self, shot: CinematicShot) -> str:
        """Build subject motion description."""
        parts = []

        if shot.character_actions:
            for action in shot.character_actions:
                mapped = ACTION_MOTION_MAP.get(action.lower(), action)
                parts.append(mapped)

        if shot.cloth_motion:
            parts.append(shot.cloth_motion)

        if not parts:
            parts.append("角色保持静止，仅有呼吸起伏")

        return "。".join(parts)

    # ---- Internal: Expression Motion ----

    def _build_expression_motion(self, shot: CinematicShot) -> str:
        """Build facial micro-expression description."""
        parts = []

        if shot.expressions:
            parts.extend(shot.expressions)
        elif shot.micro_expression:
            parts.append(shot.micro_expression)
        else:
            expr_map = {
                "angry": "眉头紧锁，眼神犀利，嘴角下沉",
                "sad": "眼神低垂，微微皱眉，嘴唇紧闭",
                "happy": "嘴角上扬，眼睛微弯，自然微笑",
                "fearful": "眼睛睁大，瞳孔收缩，呼吸急促",
                "surprised": "眉毛上扬，眼睛睁大，嘴巴微张",
                "tense": "咬紧牙关，颈部肌肉紧绷",
                "determined": "目光坚定，下巴微抬，表情沉稳",
                "calm": "面容平静，呼吸均匀",
                "excited": "眼睛发亮，表情生动，面部肌肉活跃",
                "neutral": "自然表情，轻微眨眼",
            }
            parts.append(expr_map.get(shot.emotion, "自然表情，轻微眨眼"))

        return "，".join(parts)

    # ---- Internal: Cloth & Environment ----

    def _build_cloth_environment(self, shot: CinematicShot) -> str:
        """Build cloth and environmental motion."""
        parts = []

        # Weather-based environment
        weather_env = {
            "rain": "雨水滴落，地面水花飞溅，衣物湿润贴身",
            "snow": "雪花飘落，地面覆盖积雪，呼出白气",
            "wind": "风吹动头发和衣物，树叶摇曳",
            "fog": "雾气流动，能见度降低，背景模糊",
            "storm": "狂风暴雨，树木剧烈摇晃，闪电照亮天空",
            "clear": "微风轻拂，发丝和衣摆自然飘动",
        }
        w = shot.weather.lower() if shot.weather else "clear"
        parts.append(weather_env.get(w, weather_env["clear"]))

        # Explicit cloth motion
        if shot.cloth_motion and shot.cloth_motion not in parts:
            parts.append(shot.cloth_motion)

        # VFX particles
        for vfx in shot.visual_effects:
            parts.append(vfx)

        return "，".join(parts) if parts else "静态环境，无明显风效"

    # ---- Internal: Lighting ----

    def _build_lighting(self, shot: CinematicShot) -> str:
        """Build lighting description."""
        if shot.custom_lighting:
            return shot.custom_lighting

        # Infer from time of day
        tod = shot.time_of_day.lower() if shot.time_of_day else "day"

        # Map common TOD values to our presets
        tod_map = {
            "dawn": "dawn", "morning": "morning", "noon": "noon",
            "afternoon": "afternoon", "dusk": "dusk", "night": "night",
            "day": "morning", "sunrise": "dawn", "sunset": "dusk",
            "evening": "dusk", "midnight": "night",
        }
        preset_key = tod_map.get(tod, "morning")
        preset = LIGHTING_PRESETS.get(preset_key, LIGHTING_PRESETS["morning"])
        return preset["cn"]

    # ---- Internal: VFX ----

    def _build_vfx(self, shot: CinematicShot) -> str:
        """Build VFX description."""
        parts = []

        # Emotion-based VFX
        emo_vfx = EMOTION_VFX_MAP.get(shot.emotion, {})
        if emo_vfx:
            parts.append(emo_vfx.get("cn", ""))

        # Explicit VFX
        for vfx in shot.visual_effects:
            if vfx not in parts:
                parts.append(vfx)

        return "，".join(parts) if parts else "无特殊特效"

    # ---- Internal: Sound Design ----

    def _build_sound_design(self, shot: CinematicShot) -> str:
        """Build sound design note."""
        parts = []

        if shot.dialogue:
            parts.append(f"对白：{shot.dialogue}")
        if shot.sfx:
            parts.append(f"音效：{shot.sfx}")
        if shot.bgm_mood:
            parts.append(f"BGM氛围：{shot.bgm_mood}")

        # Ambient sound based on environment
        ambient_map = {
            "rain": "雨声淅沥",
            "storm": "雷声轰鸣，风雨呼啸",
            "night": "夜晚虫鸣，远处风声",
            "wind": "风声呼啸",
            "clear": "环境底噪，轻微鸟鸣",
        }
        weather = shot.weather.lower() if shot.weather else "clear"
        ambient = ambient_map.get(weather, "")
        if ambient:
            parts.append(f"环境音：{ambient}")

        return "；".join(parts) if parts else "无特殊音效设计"

    # ---- Internal: First/Last Frame ----

    def _build_first_frame(
        self,
        shot: CinematicShot,
        prev: Optional[CinematicShot],
    ) -> str:
        """Describe the first frame state for I2V reference."""
        parts = []

        # Characters in initial state
        if shot.characters:
            parts.append(f"画面主体：{', '.join(shot.characters)}")

        # Initial pose
        if shot.character_actions:
            first_action = shot.character_actions[0]
            mapped = ACTION_MOTION_MAP.get(first_action.lower(), first_action)
            parts.append(f"初始姿态：{mapped}")

        # Scene context
        if shot.scene_description:
            parts.append(f"场景：{shot.scene_description}")

        # Lighting
        parts.append(f"灯光：{self._build_lighting(shot)}")

        # Transition from previous
        if prev and shot.transition_in != "cut":
            parts.append(f"承接上一镜头的{shot.transition_in}过渡")

        return "；".join(parts)

    def _build_last_frame(
        self,
        shot: CinematicShot,
        nxt: Optional[CinematicShot],
    ) -> str:
        """Describe the last frame state for I2V reference."""
        parts = []

        # End state of action
        if shot.character_actions:
            last_action = shot.character_actions[-1]
            mapped = ACTION_MOTION_MAP.get(last_action.lower(), last_action)
            parts.append(f"结束姿态：{mapped}")

        # Camera end position
        parts.append(f"镜头最终位置：{shot.camera_movement or '推进至主体'}")

        # Lighting at end
        parts.append(f"灯光变化：{self._build_lighting(shot)}")

        # Setup for next
        if nxt and nxt.transition_in != "cut":
            parts.append(f"为下一镜头的{nxt.transition_in}转场做准备")

        return "；".join(parts) if parts else "画面结束状态"

    # ---- Internal: Motion Strength ----

    def _infer_motion_strength(self, shot: CinematicShot) -> float:
        """Infer motion strength based on shot content."""
        base = 0.5

        # Boost for action shots
        action_keywords = ["attack", "fight", "run", "jump", "cast_spell", "draw_weapon", "fall"]
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

        # High emotion boost
        if shot.emotion in ("angry", "excited", "surprised"):
            base = max(base, 0.6)

        return round(base, 2)

    # ---- Internal: Camera Angle ----

    def _infer_camera_angle(self, shot: CinematicShot) -> str:
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
            "two_shot": "中景平视双人",
            "over_shoulder": "过肩视角",
        }
        return angle_map.get(shot.shot_type, "中景平视")

    # ---- Internal: English Prompt ----

    def _build_english_prompt(
        self,
        prompt: DirectorVideoPrompt,
        shot: CinematicShot,
    ) -> str:
        """Generate English version of the video prompt."""
        parts = []

        if prompt.action_sequence:
            parts.append(f"Action: {prompt.action_sequence}")
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
        if prompt.vfx_description:
            parts.append(f"VFX: {prompt.vfx_description}")

        parts.append(self.style)

        return "; ".join(parts) if parts else "character animation with camera movement"

    # ---- Internal: Full Prompt Synthesis ----

    def _synthesize_full(
        self,
        prompt: DirectorVideoPrompt,
        shot: CinematicShot,
    ) -> str:
        """Combine all fields into a complete prompt string."""
        sections = [
            ("# 导演思维", f"故事意图：{prompt.story_intent}\n情绪弧线：{prompt.emotional_progression}\n节奏：{prompt.pacing_note}"),
            ("# 画面描述", prompt.action_sequence),
            ("# 镜头运动", prompt.camera_motion),
            ("# 角色动作", prompt.character_motion),
            ("# 表情变化", prompt.expression_motion),
            ("# 环境特效", prompt.cloth_environment),
            ("# 灯光效果", prompt.lighting_description),
            ("# 视觉特效", prompt.vfx_description),
            ("# 声音设计", prompt.sound_design),
            ("# 首帧参考", prompt.first_frame_desc),
            ("# 尾帧参考", prompt.last_frame_desc),
        ]

        lines = []
        for label, content in sections:
            if content:
                lines.append(f"{label}\n{content}")

        return "\n\n".join(lines)

    # ---- Convenience: Build from Dict ----

    @staticmethod
    def build_from_dict(shot_dict: Dict[str, Any]) -> DirectorVideoPrompt:
        """Build a DirectorVideoPrompt from a raw shot dictionary."""
        # Convert dict to CinematicShot
        shot = CinematicShot(
            shot_id=shot_dict.get("shot_id", ""),
            chapter=shot_dict.get("chapter", 1),
            scene=shot_dict.get("scene", 1),
            shot_num=shot_dict.get("shot", 1),
            shot_type=shot_dict.get("shot_type", "medium"),
            camera_movement=shot_dict.get("camera_movement", ""),
            focal_length=shot_dict.get("focal_length", ""),
            aperture=shot_dict.get("aperture", "f/2.8"),
            depth_of_field=shot_dict.get("depth_of_field", "shallow"),
            angle=shot_dict.get("angle", "eye_level"),
            characters=shot_dict.get("characters", []),
            character_actions=shot_dict.get("character_actions", []),
            expressions=shot_dict.get("expressions", []),
            emotion=shot_dict.get("emotion", "neutral"),
            scene_description=shot_dict.get("scene_description", ""),
            time_of_day=shot_dict.get("time_of_day", "day"),
            weather=shot_dict.get("weather", "clear"),
            custom_lighting=shot_dict.get("lighting", ""),
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
        builder = DirectorVideoPromptBuilder()
        return builder.build_from_shot(shot)
