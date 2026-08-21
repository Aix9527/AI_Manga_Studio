"""Script Generator — Novel to Structured Video Script.

Based on the Krene tutorial workflow (Step 02), this module converts raw novel
text into a structured video script following the tutorial's format:

  【故事概要】 — 3-5 sentence story summary
  【主要角色】 — Character profiles with appearance, personality, role
  【场景N】 — Scene breakdown with:
    镜头N
      镜头类型: (close-up, wide shot, tracking, etc.)
      画面描述: (visual description, filmable)
      角色动作: (character actions)
      环境细节: (environment details)
      旁白/对白: (narration/dialogue)
      时长: (duration in seconds)

The generator uses rule-based parsing by default, with an optional LLM hook
for richer script generation when an API provider is available.

Tutorial reference:
  https://www.krene.com/blog/ai-video-comic-drama-tutorial
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.production.llm_parser import (
    NovelTextParser,
    ParsedNovel,
    ParsedEpisode,
    ParsedScene,
    ANTI_MOSAIC_NEGATIVE,
    STYLE_ANCHOR,
    QUALITY_BOOSTERS,
    CAMERA_BY_SHOT_TYPE,
    DURATION_BY_SHOT_TYPE,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Shot type mapping (Chinese → English for prompts)
# ─────────────────────────────────────────────────────────────────────────────

SHOT_TYPE_CN_TO_EN: dict[str, str] = {
    "特写": "extreme close-up shot",
    "近景": "close-up shot",
    "中景": "medium shot",
    "全景": "wide shot",
    "远景": "long shot / establishing shot",
    "推镜": "push-in / dolly-in shot",
    "拉镜": "pull-back / dolly-out shot",
    "跟拍": "tracking shot",
    "俯瞰": "aerial / overhead shot",
    "仰视": "low-angle shot",
    "手持": "handheld shot",
    "蒙太奇": "montage sequence",
}

# Shot type priority for classification (most specific first)
SHOT_TYPE_PATTERNS: list[tuple[str, list[str]]] = [
    ("extreme close-up", ["特写", "大特写", "extreme close"]),
    ("close-up", ["近景", "面部", "close-up", "close up"]),
    ("medium shot", ["中景", "半身", "medium shot"]),
    ("wide shot", ["全景", "全貌", "wide shot", "full shot"]),
    ("establishing shot", ["远景", "开场", "establishing", "long shot"]),
    ("tracking shot", ["跟拍", "跟踪", "tracking", "follow"]),
    ("push-in", ["推镜", "推进", "push-in", "dolly-in"]),
    ("pull-back", ["拉镜", "后退", "pull-back", "dolly-out"]),
    ("aerial shot", ["俯瞰", "鸟瞰", "航拍", "aerial", "overhead"]),
    ("low-angle", ["仰视", "仰拍", "low-angle"]),
    ("handheld", ["手持", "晃动", "handheld", "shaky"]),
    ("montage", ["蒙太奇", "混剪", "montage"]),
]


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScriptShot:
    """A single shot in the structured script (tutorial format)."""

    shot_id: str
    scene_id: str
    shot_type_cn: str = "中景"  # Chinese shot type
    shot_type_en: str = "medium shot"  # English equivalent for prompts
    visual_description: str = ""  # 画面描述
    character_action: str = ""  # 角色动作
    environment_detail: str = ""  # 环境细节
    narration_dialogue: str = ""  # 旁白/对白
    duration: float = 5.0  # 时长 (seconds)
    characters: list[str] = field(default_factory=list)
    camera_movement: str = ""  # Camera movement suggestion
    mood: str = "neutral"

    @property
    def is_dialogue(self) -> bool:
        """Check if this shot contains dialogue."""
        return bool(self.narration_dialogue) and any(
            c in self.narration_dialogue for c in '\u201c\u201d\u300c\u300d\u2018\u2019'
        )

    def to_prompt_dict(self) -> dict[str, str]:
        """Convert to a prompt-friendly dictionary for image/video generation."""
        return {
            "shot_type": self.shot_type_en,
            "visual_description": self.visual_description,
            "character_action": self.character_action,
            "environment": self.environment_detail,
            "mood": self.mood,
            "camera": self.camera_movement or self.shot_type_en,
            "narration": self.narration_dialogue,
        }


@dataclass
class ScriptScene:
    """A scene containing multiple shots."""

    scene_id: str
    scene_description: str = ""
    location: str = ""
    mood: str = "neutral"
    shots: list[ScriptShot] = field(default_factory=list)


@dataclass
class CharacterProfile:
    """Character design profile (tutorial Step 03 format)."""

    name: str
    role: str = "配角"  # 主角/反派/配角
    age_gender: str = ""
    appearance: str = ""
    clothing: str = ""
    personality: str = ""
    behavior: str = ""
    # Generated fields for image consistency
    image_prompt: str = ""
    reference_image: str = ""  # Path to reference image (filled later)

    def to_description(self) -> str:
        """Generate a description string for prompt building."""
        parts = [self.name, self.age_gender, self.appearance, self.clothing]
        return ", ".join(p for p in parts if p)


@dataclass
class VideoScript:
    """Complete structured video script (tutorial format)."""

    title: str = ""
    summary: str = ""  # 故事概要
    characters: list[CharacterProfile] = field(default_factory=list)
    scenes: list[ScriptScene] = field(default_factory=list)
    total_duration: float = 0.0
    raw_text: str = ""  # Original novel text

    @property
    def total_shots(self) -> int:
        return sum(len(s.shots) for s in self.scenes)

    @property
    def character_names(self) -> list[str]:
        return [c.name for c in self.characters]


# ─────────────────────────────────────────────────────────────────────────────
# Script Generator
# ─────────────────────────────────────────────────────────────────────────────

class ScriptGenerator:
    """Generates a structured video script from novel text.

    Implements the tutorial's Step 02 workflow:
    1. Parse novel into episodes and scenes (reuses NovelTextParser)
    2. Generate story summary
    3. Extract character profiles
    4. Break each scene into structured shots with:
       - Shot type (镜头类型)
       - Visual description (画面描述)
       - Character action (角色动作)
       - Environment detail (环境细节)
       - Narration/dialogue (旁白/对白)
       - Duration (时长)
    """

    def __init__(self, use_nlp: bool = True) -> None:
        self.parser = NovelTextParser(use_nlp=use_nlp)

    def generate(self, novel_text: str, title: str = "") -> VideoScript:
        """Generate a complete structured video script from novel text.

        Args:
            novel_text: Raw novel text (Chinese or English).
            title: Optional title override.

        Returns:
            VideoScript with summary, characters, and structured scenes/shots.
        """
        # Parse novel using existing LLM parser
        parsed = self.parser.parse(novel_text, title=title)

        # Build story summary
        summary = self._generate_summary(parsed)

        # Build character profiles
        characters = self._build_character_profiles(parsed)

        # Build structured scenes with shots
        scenes = self._build_scenes(parsed)

        total_duration = sum(
            shot.duration
            for scene in scenes
            for shot in scene.shots
        )

        script = VideoScript(
            title=parsed.title or title or "未命名小说",
            summary=summary,
            characters=characters,
            scenes=scenes,
            total_duration=total_duration,
            raw_text=novel_text[:5000],  # Keep first 5000 chars for reference
        )

        logger.info(
            "Generated script: %s — %d scenes, %d shots, %.1fs total, %d characters",
            script.title, len(scenes), script.total_shots,
            total_duration, len(characters),
        )

        return script

    def _generate_summary(self, parsed: ParsedNovel) -> str:
        """Generate a 3-5 sentence story summary."""
        # Collect first few scenes from first episode for summary
        first_ep = parsed.episodes[0] if parsed.episodes else None
        if not first_ep or not first_ep.scenes:
            return f"这是一部关于{parsed.title}的故事。"

        # Extract key plot points from first and last scenes
        first_scene = first_ep.scenes[0]
        last_scene = first_ep.scenes[-1] if len(first_ep.scenes) > 1 else None

        summary_parts = []
        if first_scene:
            # Clean up narration for summary
            narration = first_scene.narration[:80]
            summary_parts.append(narration)

        if last_scene and last_scene.scene_id != first_scene.scene_id:
            narration = last_scene.narration[:80]
            if narration and narration != first_scene.narration[:80]:
                summary_parts.append(narration)

        # Add character context
        if parsed.characters:
            char_names = list(parsed.characters.keys())[:3]
            char_str = "、".join(char_names)
            summary_parts.append(f"主要角色包括{char_str}。")

        if not summary_parts:
            summary_parts.append(f"故事围绕{parsed.title}展开。")

        # Ensure 3-5 sentences
        summary = " ".join(summary_parts)
        if len(summary) < 20:
            summary = f"这是一部关于{parsed.title}的故事，充满了紧张刺激的剧情和丰富的人物情感。"

        return summary

    def _build_character_profiles(self, parsed: ParsedNovel) -> list[CharacterProfile]:
        """Build character profiles from parsed novel data."""
        profiles: list[CharacterProfile] = []

        for name, styling in parsed.characters.items():
            # Parse the styling description into structured fields
            profile = self._parse_character_styling(name, styling, parsed.raw_text if hasattr(parsed, 'raw_text') else "")
            profiles.append(profile)

        # Sort by importance (protagonist first, then by appearance order)
        role_order = {"主角": 0, "反派": 1, "配角": 2}
        profiles.sort(key=lambda p: role_order.get(p.role, 3))

        return profiles

    def _parse_character_styling(self, name: str, styling: str, full_text: str) -> CharacterProfile:
        """Parse a character styling string into a structured profile."""
        profile = CharacterProfile(name=name)

        # Extract gender
        if "young woman" in styling or "female" in styling.lower():
            profile.age_gender = "女"
        elif "young man" in styling or "male" in styling.lower():
            profile.age_gender = "男"
        else:
            profile.age_gender = "未知"

        # Extract appearance hints from styling
        appearance_parts = []
        for keyword, en in [
            ("silver hair", "银发"), ("white hair", "白发"), ("black hair", "黑发"),
            ("blonde hair", "金发"), ("blue eyes", "蓝眼"), ("golden eyes", "金眼"),
            ("red eyes", "红眼"), ("green eyes", "绿眼"),
            ("wearing armor", "身穿铠甲"), ("wearing flowing robes", "身穿法袍"),
            ("wearing elegant dress", "身穿长裙"),
        ]:
            if keyword in styling:
                appearance_parts.append(en)

        profile.appearance = "，".join(appearance_parts) if appearance_parts else "外貌特征不明显"

        # Extract role
        if "warrior" in styling:
            profile.role = "主角"
            profile.clothing = "战斗服装，铠甲"
        elif "mage" in styling:
            profile.role = "主角"
            profile.clothing = "法师长袍，飘逸"
        elif "nobility" in styling:
            profile.role = "配角"
            profile.clothing = "贵族服饰，华丽"
        else:
            profile.role = "配角"
            profile.clothing = "日常服装"

        # Generate image prompt for character consistency
        profile.image_prompt = self._build_character_image_prompt(profile, styling)

        return profile

    def _build_character_image_prompt(self, profile: CharacterProfile, styling: str) -> str:
        """Build a prompt for generating character reference images.

        Follows the tutorial's Step 03 format for character design prompts.
        """
        parts = [
            styling,  # Original styling from parser
            "character design sheet",
            "full body character art",
            "concept design",
            "high detail",
            "cinematic lighting",
            "4K quality",
            "consistent appearance, same face",
            "clean background",
            STYLE_ANCHOR,
        ]
        return ", ".join(p for p in parts if p)

    def _build_scenes(self, parsed: ParsedNovel) -> list[ScriptScene]:
        """Build structured scenes with shots from parsed novel."""
        scenes: list[ScriptScene] = []

        for episode in parsed.episodes:
            for parsed_scene in episode.scenes:
                script_scene = self._convert_scene(parsed_scene)
                scenes.append(script_scene)

        return scenes

    def _convert_scene(self, parsed_scene: ParsedScene) -> ScriptScene:
        """Convert a ParsedScene to a ScriptScene with structured shots."""
        scene = ScriptScene(
            scene_id=parsed_scene.scene_id,
            scene_description=parsed_scene.description[:200],
            location=parsed_scene.location,
            mood=parsed_scene.mood,
        )

        # Determine number of shots for this scene (1-3 based on content)
        desc_len = len(parsed_scene.description)
        if desc_len > 200:
            num_shots = 3
        elif desc_len > 100:
            num_shots = 2
        else:
            num_shots = 1

        # Split scene description into shot segments
        segments = self._split_scene_into_shots(parsed_scene, num_shots)

        for i, segment in enumerate(segments):
            shot = self._build_shot(parsed_scene, segment, i + 1)
            scene.shots.append(shot)

        return scene

    def _split_scene_into_shots(self, scene: ParsedScene, num_shots: int) -> list[str]:
        """Split a scene's text into shot-sized segments."""
        text = scene.description
        if num_shots <= 1:
            return [text]

        # Split by sentences
        sentences = re.split(r"(?<=[。！？!?…])", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) <= num_shots:
            # Not enough sentences, duplicate last
            while len(sentences) < num_shots:
                sentences.append(sentences[-1] if sentences else text)

        # Distribute sentences across shots
        segments: list[str] = []
        per_shot = max(1, len(sentences) // num_shots)
        for i in range(num_shots):
            start = i * per_shot
            end = start + per_shot if i < num_shots - 1 else len(sentences)
            segment = "".join(sentences[start:end])
            if not segment:
                segment = sentences[-1] if sentences else text
            segments.append(segment)

        return segments

    def _build_shot(self, scene: ParsedScene, segment: str, shot_index: int) -> ScriptShot:
        """Build a structured ScriptShot from a scene segment."""
        shot_id = f"{scene.scene_id}_shot{shot_index}"

        # Determine shot type
        shot_type_cn, shot_type_en = self._classify_shot_type(segment, scene.shot_type)

        # Extract visual description (画面描述)
        visual_desc = self._extract_visual_description(segment, scene)

        # Extract character action (角色动作)
        char_action = self._extract_character_action(segment, scene.characters)

        # Extract environment detail (环境细节)
        env_detail = self._extract_environment(segment, scene.location)

        # Extract narration/dialogue (旁白/对白)
        narration = self._extract_narration(segment, scene.narration)

        # Camera movement
        camera = CAMERA_BY_SHOT_TYPE.get(scene.shot_type, "medium shot, subtle parallax")

        # Duration
        duration = DURATION_BY_SHOT_TYPE.get(scene.shot_type, 5.0)

        return ScriptShot(
            shot_id=shot_id,
            scene_id=scene.scene_id,
            shot_type_cn=shot_type_cn,
            shot_type_en=shot_type_en,
            visual_description=visual_desc,
            character_action=char_action,
            environment_detail=env_detail,
            narration_dialogue=narration,
            duration=duration,
            characters=scene.characters[:3],
            camera_movement=camera,
            mood=scene.mood,
        )

    def _classify_shot_type(self, text: str, fallback_type: str) -> tuple[str, str]:
        """Classify shot type from text, returning (Chinese, English) pair."""
        text_lower = text.lower()

        for cn_type, en_type in [("特写", "extreme close-up"), ("近景", "close-up"),
                                   ("中景", "medium shot"), ("全景", "wide shot"),
                                   ("远景", "establishing shot")]:
            for pattern in SHOT_TYPE_PATTERNS:
                if pattern[0] == en_type:
                    if any(kw in text or kw in text_lower for kw in pattern[1]):
                        return cn_type, en_type

        # Use fallback from scene type
        type_map = {
            "establishing": ("远景", "establishing shot"),
            "dialogue": ("中景", "medium shot"),
            "action": ("跟拍", "tracking shot"),
            "emotional": ("近景", "close-up shot"),
            "transition": ("全景", "wide shot"),
            "narration": ("中景", "medium shot"),
        }
        return type_map.get(fallback_type, ("中景", "medium shot"))

    def _extract_visual_description(self, segment: str, scene: ParsedScene) -> str:
        """Extract a filmable visual description from the segment."""
        # Clean up the text
        desc = re.sub(r'["""''「」『』]', '', segment)
        desc = re.sub(r'\s+', ' ', desc).strip()

        # Limit length
        if len(desc) > 120:
            desc = desc[:120].rstrip("，、；：. ") + "..."

        return desc

    def _extract_character_action(self, segment: str, characters: list[str]) -> str:
        """Extract character action description."""
        actions: list[str] = []

        action_map = {
            "拔剑": "拔剑出鞘，剑身闪光",
            "握拳": "握紧双拳，神情坚定",
            "冲锋": "向前冲锋，步伐有力",
            "转身": "转身回望",
            "凝视": "凝视前方",
            "微笑": "微微一笑",
            "流泪": "泪水滑落脸颊",
            "怒吼": "怒吼出声",
            "施法": "双手凝聚灵力，光芒闪烁",
            "跪": "单膝跪地",
            "站起": "缓缓站起",
        }

        for cn, action_desc in action_map.items():
            if cn in segment:
                # Find which character is doing the action
                for char in characters:
                    if char in segment:
                        actions.append(f"{char}{action_desc}")
                        break
                else:
                    actions.append(action_desc)

        if not actions:
            # Generic action based on dialogue
            if any(marker in segment for marker in [""", """, "「", "」"]):
                for char in characters:
                    if char in segment:
                        actions.append(f"{char}说话")
                        break

        return "；".join(actions[:2]) if actions else "角色静止站立"

    def _extract_environment(self, segment: str, location: str) -> str:
        """Extract environment details from the segment."""
        env_parts: list[str] = []

        # Add location
        if location:
            env_parts.append(location)

        # Detect time of day
        time_map = {
            "清晨": "晨光", "黄昏": "夕阳", "夜晚": "夜色",
            "午夜": "深夜", "黎明": "破晓", "白天": "日光",
        }
        for cn, desc in time_map.items():
            if cn in segment:
                env_parts.append(desc)
                break

        # Detect weather
        weather_map = {
            "风": "风吹", "雨": "雨落", "雪": "雪飘",
            "云": "云涌", "雷": "雷鸣",
        }
        for cn, desc in weather_map.items():
            if cn in segment:
                env_parts.append(desc)
                break

        return "，".join(env_parts[:3]) if env_parts else "环境细节未指定"

    def _extract_narration(self, segment: str, scene_narration: str) -> str:
        """Extract narration/dialogue from the segment."""
        # Extract quoted dialogue
        dialogue_matches = re.findall(r'[""「」](.*?)[""」」]', segment)
        if dialogue_matches:
            return "；".join(dialogue_matches[:3])

        # Fall back to scene narration
        if scene_narration:
            return scene_narration[:60]

        # Use cleaned segment as narration
        cleaned = re.sub(r'["""''「」『』]', '', segment)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned[:60] if cleaned else ""


# ─────────────────────────────────────────────────────────────────────────────
# Convenience functions
# ─────────────────────────────────────────────────────────────────────────────

def generate_script(novel_text: str, title: str = "") -> VideoScript:
    """Convenience wrapper: generate a structured video script from novel text."""
    generator = ScriptGenerator()
    return generator.generate(novel_text, title=title)


def script_to_plan_shots(script: VideoScript) -> list[dict[str, Any]]:
    """Convert a VideoScript to shot dicts compatible with the production pipeline.

    Each shot in the script becomes one production shot with:
    - Structured positive_prompt following tutorial format
    - Anti-mosaic negative_prompt
    - Camera, narration, duration from script structure
    """
    shots: list[dict[str, Any]] = []
    shot_number = 0

    for scene in script.scenes:
        for script_shot in scene.shots:
            shot_number += 1

            # Build structured positive prompt following tutorial format:
            # 镜头类型 + 角色动作 + 场景环境 + 情绪氛围 + 画面风格
            prompt_parts = [
                STYLE_ANCHOR,
                script_shot.shot_type_en,
                script_shot.camera_movement,
                script_shot.visual_description,
            ]

            # Add character descriptions
            for char_name in script_shot.characters:
                char_profile = next(
                    (c for c in script.characters if c.name == char_name), None
                )
                if char_profile:
                    prompt_parts.append(char_profile.to_description())
                else:
                    prompt_parts.append(char_name)

            # Add environment and mood
            if script_shot.environment_detail:
                prompt_parts.append(script_shot.environment_detail)
            if script_shot.mood and script_shot.mood != "neutral":
                prompt_parts.append(script_shot.mood)

            # Quality boosters
            prompt_parts.append(QUALITY_BOOSTERS)

            positive_prompt = ", ".join(
                p for p in prompt_parts if p and p.strip()
            )

            shots.append({
                "id": script_shot.shot_id,
                "shot_number": shot_number,
                "description": script_shot.visual_description,
                "duration": script_shot.duration,
                "camera": script_shot.camera_movement or script_shot.shot_type_en,
                "characters": list(script_shot.characters),
                "dialogue": [],
                "sfx": [],
                "positive_prompt": positive_prompt,
                "negative_prompt": ANTI_MOSAIC_NEGATIVE,
                "narration": script_shot.narration_dialogue,
                "transition": "fade",
                "seed": abs(hash(script_shot.shot_id)) % 1000000,
                # Tutorial-specific structured fields
                "shot_type_cn": script_shot.shot_type_cn,
                "shot_type_en": script_shot.shot_type_en,
                "character_action": script_shot.character_action,
                "environment_detail": script_shot.environment_detail,
            })

    return shots


def script_to_json(script: VideoScript) -> dict[str, Any]:
    """Serialize a VideoScript to a JSON-serializable dictionary."""
    return {
        "title": script.title,
        "summary": script.summary,
        "characters": [
            {
                "name": c.name,
                "role": c.role,
                "age_gender": c.age_gender,
                "appearance": c.appearance,
                "clothing": c.clothing,
                "personality": c.personality,
                "behavior": c.behavior,
                "image_prompt": c.image_prompt,
            }
            for c in script.characters
        ],
        "scenes": [
            {
                "scene_id": s.scene_id,
                "description": s.scene_description,
                "location": s.location,
                "mood": s.mood,
                "shots": [
                    {
                        "shot_id": shot.shot_id,
                        "shot_type_cn": shot.shot_type_cn,
                        "shot_type_en": shot.shot_type_en,
                        "visual_description": shot.visual_description,
                        "character_action": shot.character_action,
                        "environment_detail": shot.environment_detail,
                        "narration_dialogue": shot.narration_dialogue,
                        "duration": shot.duration,
                        "characters": shot.characters,
                        "camera_movement": shot.camera_movement,
                        "mood": shot.mood,
                    }
                    for shot in s.shots
                ],
            }
            for s in script.scenes
        ],
        "total_duration": script.total_duration,
        "total_shots": script.total_shots,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    _sample = (
        "\u7b2c\u4e00\u7ae0 \u98ce\u8d77\n"
        "\u82cf\u7483\u7ad9\u5728\u60ac\u5d16\u8fb9\uff0c\u94f6\u53d1\u5728\u98ce\u4e2d\u98de\u626c\u3002"
        "\u5979\u51dd\u89c6\u7740\u8fdc\u65b9\u7684\u57ce\u5e02\uff0c\u84dd\u773c\u4e2d\u5012\u6620\u7740\u591c\u7a7a\u7684\u661f\u5149\u3002\n"
        "\u201c\u53c8\u6765\u4e86\u3002\u201d\u82cf\u7483\u4f4e\u58f0\u9053\uff0c\u63e1\u7d27\u4e86\u624b\u4e2d\u7684\u957f\u5251\u3002\n"
        "\u7a81\u7136\uff0c\u4e00\u9053\u9ed1\u5f71\u4ece\u5929\u800c\u964d\u3002"
        "\u6797\u8f69\u51b2\u4e86\u8fc7\u6765\uff0c\u62d4\u5251\u51fa\u9798\uff0c\u5251\u8eab\u95ea\u70c1\u7740\u5bd2\u5149\u3002\n"
        "\u201c\u5c0f\u5fc3\uff01\u201d\u6797\u8f69\u558a\u9053\uff0c\u6321\u5728\u82cf\u7483\u8eab\u524d\u3002\n"
        "\u4e24\u4eba\u5e76\u80a9\u800c\u7acb\uff0c\u9762\u5bf9\u7740\u9010\u6e10\u903c\u8fd1\u7684\u5996\u9b54\u3002"
        "\u6218\u6597\u4e00\u89e6\u5373\u53d1\u3002\n"
    ) * 8

    _script = generate_script(_sample, title="\u98ce\u8d77\u5f55")
    print(f"Title: {_script.title}")
    print(f"Summary: {_script.summary}")
    print(f"Characters: {[c.name for c in _script.characters]}")
    print(f"Scenes: {len(_script.scenes)}, Shots: {_script.total_shots}")
    print(f"Total duration: {_script.total_duration:.1f}s")
    for scene in _script.scenes[:2]:
        print(f"\n  Scene {scene.scene_id}: {scene.scene_description[:60]}...")
        for shot in scene.shots:
            print(f"    {shot.shot_id} [{shot.shot_type_cn}] {shot.duration}s")
            print(f"      \u753b\u9762: {shot.visual_description[:60]}")
            print(f"      \u52a8\u4f5c: {shot.character_action[:60]}")
