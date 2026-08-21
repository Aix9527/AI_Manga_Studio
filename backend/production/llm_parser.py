"""LLM-based novel text parser for the AI Manga Studio production pipeline.

Parses raw novel text into a structured ``ParsedNovel`` (episodes -> scenes ->
shots) ready for automatic video generation. Each scene yields a cinematic
English positive prompt, an anti-mosaic negative prompt, the original Chinese
narration, a camera-movement suggestion and a deterministic seed.

Design goals
------------
* **Self-contained** — the rule-based parser is the primary path and requires no
  external API keys and no third-party packages. It works on a fresh checkout.
* **Optional NLP enhancement** — when the existing Chinese NLP layer
  (``backend.nlp``: jieba segmenter / NER / emotion mapper) is importable, the
  parser reuses it for sharper segmentation, name detection and mood mapping.
  Any import/instantiation failure degrades silently to the built-in heuristics.
* **Optional LLM enhancement** — an ``LLMProvider`` can be plugged in to enrich
  the generated prompts. When no provider is configured the parser falls back to
  the rule-based output, satisfying the "no API key required" constraint.

Segmentation parameters
-----------------------
* Episode splitting: ~3000-5000 Chinese characters per episode (≈10 minutes).
* Scene splitting:    ~150-250 Chinese characters per scene  (≈12-20 seconds).
* Each episode yields 20-40 scenes.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Segmentation parameters
# ─────────────────────────────────────────────────────────────────────────────

EPISODE_MIN_CHARS = 3000      # lower bound for auto-split episodes
EPISODE_MAX_CHARS = 5000      # upper bound for auto-split episodes
EPISODE_TARGET_CHARS = 4000   # preferred episode size
EPISODE_TARGET_SECONDS = 600  # ≈10 minutes

SCENE_MIN_CHARS = 150
SCENE_MAX_CHARS = 250
SCENE_TARGET_CHARS = 200
SCENE_TARGET_SECONDS = 15     # midpoint of 12-20s

# Sentence / paragraph boundaries for Chinese and English prose.
SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?…\n])")
PARAGRAPH_SPLIT = re.compile(r"\n{1,}")
CHAPTER_HEADING = re.compile(
    r"(?m)^\s*(第[零〇一二三四五六七八九十百千万两\d]+[章节卷部回话][^\r\n]*"
    r"|Chapter\s+\d+[^\r\n]*|CH\.\s*\d+[^\r\n]*)\s*$"
)

# ─────────────────────────────────────────────────────────────────────────────
# Prompt building blocks
# ─────────────────────────────────────────────────────────────────────────────

# Style anchor reused from backend.production.plan_builder (kept local so the
# module stays self-contained).
STYLE_ANCHOR = (
    "photorealistic live-action Chinese cinema, realistic Chinese cast, "
    "natural skin texture, physically accurate fabric, cinematic lighting, "
    "volumetric atmosphere, 35mm film still, controlled depth of field, "
    "high dynamic range, subtle film grain"
)

# Quality boosters appended to every positive prompt.
QUALITY_BOOSTERS = (
    "cinematic lighting, 8k uhd, photorealistic, highly detailed, sharp focus, "
    "film grain, depth of field, volumetric lighting, dramatic composition, "
    "professional color grading, masterpiece"
)

# Anti-mosaic + quality-control negative prompt. Always included verbatim.
ANTI_MOSAIC_NEGATIVE = (
    "mosaic, pixelated, blocky, low quality, worst quality, blur, deformed, "
    "disfigured, extra limbs, bad anatomy, malformed hands, duplicate person, "
    "anime, manga, illustration, cartoon, 3d render, plastic skin, doll face, "
    "text, logo, subtitle, watermark"
)

# Camera movement suggestion per shot type.
CAMERA_BY_SHOT_TYPE: dict[str, str] = {
    "establishing": "aerial establishing shot, slow push-in",
    "dialogue": "medium close-up, static with subtle parallax",
    "action": "dynamic tracking shot, handheld pan",
    "emotional": "slow push-in, shallow depth of field",
    "transition": "slow pull back, dolly movement",
    "narration": "slow pan across wide scene",
}

# Suggested shot duration (seconds) per shot type.
DURATION_BY_SHOT_TYPE: dict[str, float] = {
    "establishing": 6.0,
    "dialogue": 4.0,
    "action": 3.0,
    "emotional": 5.0,
    "transition": 2.0,
    "narration": 5.0,
}

# Shot-type classification keywords (Chinese). The first matching category wins.
SHOT_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    # Explicit wide-shot / viewing descriptors only. Generic location nouns
    # (城市, 山脉, 森林, ...) are handled by LOCATION_MAP and must NOT classify
    # a dialogue/action scene as an establishing shot.
    "establishing": (
        "开场", "远眺", "俯瞰", "鸟瞰", "全景", "远景", "苍穹", "天地",
    ),
    "dialogue": (
        "说道", "问道", "答道", "喊道", "笑道", "怒道", "冷道", "低声道",
        "开口", "回答", "质问", "反驳", "呢喃", "嘀咕",
    ),
    # 2-char combat/movement verbs are unambiguous; the single-char verbs kept
    # here (跑/跳/斩/砍/刺/劈) are almost always action. Noisy single chars
    # (打→打转, 冲→冲突, 击→击中, 射→反射, 挥→挥发) are deliberately omitted.
    "action": (
        "拔剑", "握拳", "冲锋", "跃起", "格挡", "闪避", "追击", "施法", "召唤",
        "战斗", "交手", "出招", "跑", "跳", "斩", "砍", "刺", "劈",
    ),
    "emotional": (
        "哭", "泪", "悲", "哀", "怒", "恐", "惊", "颤抖", "心痛", "绝望",
        "微笑", "欣慰", "心动", "孤独", "思念", "凄凉", "心碎", "流泪",
    ),
    "transition": (
        "第二天", "次日", "翌日", "数日后", "几日后", "此时", "此刻", "与此同时",
        "另一边", "镜头转向", "多年以后", "清晨", "黄昏", "深夜", "黎明",
        "场景转换", "话说", "却说",
    ),
}

# Location detection (Chinese keyword -> English setting fragment).
LOCATION_MAP: dict[str, tuple[tuple[str, ...], str]] = {
    "interior": (("室内", "房间", "卧室", "客厅", "书房", "厨房"), "interior room, warm practical lighting"),
    "palace": (("宫殿", "大殿", "殿堂", "朝堂"), "grand palace hall, ornate columns, golden light"),
    "urban": (("城市", "街道", "广场", "市场", "城楼", "城墙"), "city street, urban environment"),
    "outdoor": (("户外", "野外", "草原", "海岸", "荒原"), "open outdoor landscape"),
    "forest": (("森林", "树林", "密林"), "dense forest, dappled light through canopy"),
    "desert": (("沙漠", "荒漠", "戈壁"), "vast desert, harsh sun, long shadows"),
    "mountain": (("山脉", "高山", "山巅", "悬崖"), "mountain range, misty peaks"),
    "battlefield": (("战场", "擂台", "竞技场", "决斗场"), "battlefield, dust and smoke"),
    "mystical": (("秘境", "洞窟", "遗迹", "禁地", "圣殿"), "mystical realm, glowing runes, ethereal mist"),
    "school": (("学院", "宗门", "道观", "寺庙"), "academy courtyard, ancient architecture"),
    "night_sky": (("夜空", "星空", "星域", "天际"), "night sky filled with stars"),
}

# Mood detection (Chinese keyword -> English atmosphere fragment).
MOOD_MAP: dict[str, tuple[tuple[str, ...], str]] = {
    "tense": (("紧张", "危机", "危险", "攻击", "威胁", "压迫"), "tense atmosphere, dramatic tension"),
    "calm": (("平静", "安静", "宁静", "祥和", "悠然", "闲适"), "calm serene atmosphere"),
    "dramatic": (("激烈", "震撼", "爆裂", "怒吼", "轰鸣", "爆发"), "dramatic intense scene"),
    "dark": (("黑暗", "阴影", "阴森", "邪恶", "绝望", "冰冷", "深渊"), "dark moody atmosphere, deep shadows"),
    "sad": (("悲伤", "痛苦", "流泪", "哀伤", "凄凉", "心碎"), "melancholic somber mood"),
    "hopeful": (("希望", "光明", "温暖", "微笑", "曙光", "新生"), "hopeful warm atmosphere"),
    "romantic": (("温柔", "深情", "凝视", "拥抱", "心动"), "romantic soft atmosphere"),
    "epic": (("宏大", "壮阔", "星辰", "天地", "苍穹", "万古"), "epic grand scale"),
}

# Common Chinese surnames for the rule-based name detector.
COMMON_SURNAMES = (
    "林苏王张刘陈杨赵黄周吴徐孙胡朱高何郭马罗梁宋郑谢韩唐冯于叶萧程曹袁邓许"
    "傅沈曾彭吕卢蒋蔡贾丁魏薛潘戴夏钟汪田任姜方石姚谭廖邹熊金陆郝孔白崔康毛"
)

# Speech / action verb suffixes that signal a preceding token is a character
# name, e.g. "张三说", "李四看着", "苏璃冷笑".
NAME_ACTION_SUFFIXES = (
    "说", "道", "问", "答", "喊", "叫", "笑", "怒", "冷", "低", "叹", "看",
    "望", "盯", "转", "站", "坐", "走", "跑", "冲", "拔", "握", "抬", "低",
    "皱", "凝", "闭", "睁", "挥", "推", "拉", "抱", "抓", "跪", "倒",
)

# Stop-words that the surname heuristic must reject as name candidates.
NAME_STOPWORDS = {
    "我们", "他们", "你们", "她们", "它们", "这个", "那个", "这里", "那里",
    "什么", "怎么", "为什么", "于是", "然后", "然而", "但是", "虽然", "因为",
    "所以", "如果", "而且", "不仅", "不过", "其实", "突然", "忽然", "此时",
    "此刻", "于是是", "可以", "已经", "没有", "自己", "知道", "起来", "出来",
    "过来", "一定", "之后", "以后", "时候", "现在", "之前", "以前",
}

# Gender hints for character description generation.
GENDER_HINTS: dict[str, tuple[tuple[str, ...], str]] = {
    "male": (("他", "少年", "青年", "男子", "男人", "公子", "少爷", "将军", "师父"), "young man"),
    "female": (("她", "少女", "女子", "女人", "姑娘", "小姐", "公主", "侍女"), "young woman"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ParsedScene:
    """A single parsed scene — becomes one shot group in the production plan."""

    scene_id: str
    episode_id: str
    description: str
    characters: list[str] = field(default_factory=list)
    location: str = ""
    mood: str = "neutral"
    shot_type: str = "narration"  # establishing, dialogue, action, emotional, transition, narration
    narration: str = ""
    positive_prompt: str = ""
    negative_prompt: str = ANTI_MOSAIC_NEGATIVE
    camera: str = "slow pan across wide scene"
    seed: int = 0
    duration_hint: float = SCENE_TARGET_SECONDS


@dataclass
class ParsedEpisode:
    """A single episode (~10 minutes) composed of 20-40 scenes."""

    episode_id: str
    title: str
    scenes: list[ParsedScene] = field(default_factory=list)
    total_estimated_duration: float = 0.0


@dataclass
class ParsedNovel:
    """Top-level parse result: episodes, a global character registry and timing."""

    title: str = ""
    episodes: list[ParsedEpisode] = field(default_factory=list)
    characters: dict[str, str] = field(default_factory=dict)  # name -> styling description
    total_estimated_duration: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Optional LLM provider hook
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class LLMProvider(Protocol):
    """Minimal protocol for an optional LLM enrichment backend.

    Implementations may call any external API. The parser never requires one —
    when ``enhance_scene`` raises or returns an empty mapping, the rule-based
    result is kept unchanged.
    """

    def enhance_scene(self, scene_text: str, context: dict[str, Any]) -> dict[str, Any]:
        """Return optional overrides, e.g. ``{"positive_prompt": ..., "shot_type": ...}``.

        Keys that may be returned: ``positive_prompt``, ``negative_prompt``,
        ``shot_type``, ``camera``, ``mood``, ``location``, ``narration``.
        """
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Concrete LLM Provider implementations (GPT recommendation: cloud API)
# ─────────────────────────────────────────────────────────────────────────────

class DeepSeekLLMProvider:
    """LLM provider using DeepSeek API for novel text enrichment.

    DeepSeek API is recommended for Chinese novel parsing due to its
    strong Chinese language understanding and affordable pricing.

    Requires DEEPSEEK_API_KEY environment variable.
    Falls back silently when API key is not set.
    """

    def __init__(self, api_key: str = "", model: str = "deepseek-chat") -> None:
        import os
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = model
        self.base_url = "https://api.deepseek.com/v1/chat/completions"

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def enhance_scene(self, scene_text: str, context: dict[str, Any]) -> dict[str, Any]:
        if not self.is_available:
            return {}

        try:
            import httpx
            import json

            # Tutorial-structured system prompt (Krene format)
            system_prompt = (
                "You are a professional AI comic drama storyboard designer.\n"
                "Given a Chinese novel scene, generate a structured JSON response with:\n"
                "1. \"english_prompt\": A cinematic English prompt combining:\n"
                "   - Shot type and camera movement (e.g. medium shot, tracking, push-in)\n"
                "   - Character visual description (appearance, clothing, pose, expression)\n"
                "   - Environment detail (location, lighting, time of day, weather)\n"
                "   - Mood atmosphere\n"
                "   - Film style anchor (photorealistic, cinematic lighting, 35mm film)\n"
                "2. \"shot_type\": One of: establishing, dialogue, action, emotional, transition, narration\n"
                "3. \"camera_movement\": Camera direction in English (e.g. slow push-in, handheld tracking)\n"
                "4. \"mood\": One of: tense, calm, dramatic, dark, sad, hopeful, romantic, epic, neutral\n"
                "5. \"location\": English location description (e.g. grand palace hall, dense forest)\n"
                "6. \"character_action\": English description of what characters are doing\n"
                "7. \"visual_description\": A filmable visual description of the scene (English, max 120 chars)\n"
                "8. \"narration\": Clean narration/dialogue text (Chinese, max 80 chars)\n"
                "Respond in JSON format only."
            )

            # Build context-aware user message with tutorial structure
            user_msg_parts = [f"Scene text: {scene_text[:500]}"]
            if context:
                ctx_chars = context.get("characters", [])
                if ctx_chars:
                    user_msg_parts.append(f"Characters present: {', '.join(ctx_chars)}")
                if context.get("location"):
                    user_msg_parts.append(f"Location hint: {context['location']}")
                if context.get("mood"):
                    user_msg_parts.append(f"Mood hint: {context['mood']}")
                if context.get("shot_type"):
                    user_msg_parts.append(f"Shot type hint: {context['shot_type']}")

            response = httpx.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": "\n".join(user_msg_parts)},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 800,
                    "response_format": {"type": "json_object"},
                },
                timeout=30.0,
            )

            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                result = json.loads(content)
                # Map to expected keys with tutorial structure
                enhanced: dict[str, Any] = {
                    "positive_prompt": result.get("english_prompt", ""),
                    "shot_type": result.get("shot_type", ""),
                    "camera": result.get("camera_movement", ""),
                    "mood": result.get("mood", ""),
                    "location": result.get("location", ""),
                }
                # Add tutorial-specific structured fields
                if result.get("character_action"):
                    enhanced["character_action"] = result["character_action"]
                if result.get("visual_description"):
                    enhanced["visual_description"] = result["visual_description"]
                if result.get("narration"):
                    enhanced["narration"] = result["narration"]
                logger.debug("DeepSeek enhanced scene: %s", list(enhanced.keys()))
                return enhanced
        except Exception as exc:
            logger.warning("DeepSeek enhance_scene failed: %s", exc)

        return {}


class QwenLLMProvider:
    """LLM provider using Qwen (DashScope) API for novel text enrichment.

    Alternative to DeepSeek, uses Alibaba's Qwen model.
    Requires DASHSCOPE_API_KEY environment variable.
    """

    def __init__(self, api_key: str = "", model: str = "qwen-plus") -> None:
        import os
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        self.model = model
        self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def enhance_scene(self, scene_text: str, context: dict[str, Any]) -> dict[str, Any]:
        if not self.is_available:
            return {}

        try:
            import httpx
            import json

            # Tutorial-structured system prompt in Chinese (Qwen is optimized for Chinese)
            system_prompt = (
                "\u4f60\u662f\u4e00\u4f4d\u4e13\u4e1a\u7684AI\u6f2b\u5267\u5206\u955c\u8bbe\u8ba1\u5e08\u3002\n"
                "\u7ed9\u5b9a\u4e00\u6bb5\u4e2d\u6587\u5c0f\u8bf4\u573a\u666f\uff0c\u8bf7\u751f\u6210\u7ed3\u6784\u5316\u7684JSON\u56de\u590d\uff0c\u5305\u542b\uff1a\n"
                "1. \"english_prompt\": \u7535\u5f71\u7ea7\u82f1\u6587\u63d0\u793a\u8bcd\uff0c\u7ed3\u5408\uff1a\n"
                "   - \u955c\u5934\u7c7b\u578b\u548c\u8fd0\u52a8\u65b9\u5411\uff08\u5982 medium shot, tracking, push-in\uff09\n"
                "   - \u89d2\u8272\u89c6\u89c9\u63cf\u8ff0\uff08\u5916\u8c8c\u3001\u670d\u88c5\u3001\u59ff\u6001\u3001\u8868\u60c5\uff09\n"
                "   - \u73af\u5883\u7ec6\u8282\uff08\u5730\u70b9\u3001\u5149\u7ebf\u3001\u65f6\u95f4\u3001\u5929\u6c14\uff09\n"
                "   - \u60c5\u7eea\u6c1b\u56f4\n"
                "   - \u7535\u5f71\u98ce\u683c\u951a\u5b9a\u8bcd\uff08photorealistic, cinematic lighting, 35mm film\uff09\n"
                "2. \"shot_type\": \u955c\u5934\u7c7b\u578b\uff1aestablishing/dialogue/action/emotional/transition/narration\n"
                "3. \"camera_movement\": \u6444\u50cf\u673a\u8fd0\u52a8\u65b9\u5411\uff08\u82f1\u6587\uff0c\u5982 slow push-in, handheld tracking\uff09\n"
                "4. \"mood\": \u60c5\u7eea\uff1atense/calm/dramatic/dark/sad/hopeful/romantic/epic/neutral\n"
                "5. \"location\": \u573a\u666f\u4f4d\u7f6e\uff08\u82f1\u6587\u63cf\u8ff0\uff09\n"
                "6. \"character_action\": \u89d2\u8272\u52a8\u4f5c\u63cf\u8ff0\uff08\u82f1\u6587\uff09\n"
                "7. \"visual_description\": \u53ef\u62cd\u6444\u7684\u89c6\u89c9\u63cf\u8ff0\uff08\u82f1\u6587\uff0c\u6700\u5915120\u5b57\u7b26\uff09\n"
                "8. \"narration\": \u6e05\u7406\u540e\u7684\u65c1\u767d/\u5bf9\u767d\u6587\u672c\uff08\u4e2d\u6587\uff0c\u6700\u591a80\u5b57\u7b26\uff09\n"
                "\u53ea\u8fd4\u56deJSON\u683c\u5f0f\u3002"
            )

            # Build context-aware user message
            user_msg_parts = [f"\u573a\u666f\u6587\u672c\uff1a{scene_text[:500]}"]
            if context:
                ctx_chars = context.get("characters", [])
                if ctx_chars:
                    user_msg_parts.append(f"\u573a\u666f\u4e2d\u89d2\u8272\uff1a{', '.join(ctx_chars)}")
                if context.get("location"):
                    user_msg_parts.append(f"\u4f4d\u7f6e\u63d0\u793a\uff1a{context['location']}")
                if context.get("mood"):
                    user_msg_parts.append(f"\u60c5\u7eea\u63d0\u793a\uff1a{context['mood']}")
                if context.get("shot_type"):
                    user_msg_parts.append(f"\u955c\u5934\u7c7b\u578b\u63d0\u793a\uff1a{context['shot_type']}")

            response = httpx.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": "\n".join(user_msg_parts)},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 800,
                },
                timeout=30.0,
            )

            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                # Try to parse JSON from content
                try:
                    result = json.loads(content)
                except json.JSONDecodeError:
                    # Try to extract JSON from markdown code blocks
                    json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
                    if json_match:
                        result = json.loads(json_match.group(1))
                    else:
                        return {}

                enhanced: dict[str, Any] = {
                    "positive_prompt": result.get("english_prompt", result.get("prompt", "")),
                    "shot_type": result.get("shot_type", ""),
                    "camera": result.get("camera_movement", result.get("camera", "")),
                    "mood": result.get("mood", ""),
                    "location": result.get("location", ""),
                }
                # Add tutorial-specific structured fields
                if result.get("character_action"):
                    enhanced["character_action"] = result["character_action"]
                if result.get("visual_description"):
                    enhanced["visual_description"] = result["visual_description"]
                if result.get("narration"):
                    enhanced["narration"] = result["narration"]
                logger.debug("Qwen enhanced scene: %s", list(enhanced.keys()))
                return enhanced
        except Exception as exc:
            logger.warning("Qwen enhance_scene failed: %s", exc)

        return {}


def get_best_llm_provider() -> Optional[LLMProvider]:
    """Auto-detect and return the best available LLM provider.

    Priority order:
    1. DeepSeek API (if DEEPSEEK_API_KEY is set)
    2. Qwen/DashScope API (if DASHSCOPE_API_KEY is set)
    3. None (rule-based fallback)
    """
    import os

    if os.environ.get("DEEPSEEK_API_KEY"):
        provider = DeepSeekLLMProvider()
        if provider.is_available:
            return provider

    if os.environ.get("DASHSCOPE_API_KEY"):
        provider = QwenLLMProvider()
        if provider.is_available:
            return provider

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_chinese_text(text: str) -> bool:
    """Detect if text is primarily Chinese by CJK character ratio."""
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    total = len(text.strip()) or 1
    return cjk / total > 0.3


def _count_chars(text: str) -> int:
    """Count non-whitespace characters (Chinese-aware word count)."""
    return len(re.sub(r"\s+", "", text))


def _clean_narration(text: str, limit: int = 80) -> str:
    """Strip quotes/markdown and truncate to a narration-friendly line."""
    line = re.sub(r'["“”\'「」『』#\*]', "", text)
    line = re.sub(r"\s+", " ", line).strip()
    if len(line) > limit:
        line = line[:limit].rstrip("，、；：. ")
    return line


def _stable_seed(seed_source: str) -> int:
    """Deterministic 31-bit seed from an arbitrary string (e.g. shot_id)."""
    digest = hashlib.md5(seed_source.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % (2**31)


# ─────────────────────────────────────────────────────────────────────────────
# Optional NLP-layer integration (graceful fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _try_load_nlp() -> tuple[Optional[object], Optional[object]]:
    """Attempt to import the existing Chinese NLP layer.

    Returns ``(ner, emotion_mapper)`` where either element may be ``None`` if
    the corresponding module / dependency is unavailable. Never raises — the
    parser is fully functional without these. (The Chinese scene segmenter is
    not loaded: its transition-based scenes are coarser than the 150-250 char
    scene target, so scene splitting is always rule-based.)
    """
    ner = emotion = None
    try:
        from backend.nlp.chinese_ner import ChineseExtractor  # noqa: WPS433
        ner = ChineseExtractor()
    except Exception:
        ner = None
    try:
        from backend.nlp.emotion_mapper import EmotionMapper  # noqa: WPS433
        emotion = EmotionMapper()
    except Exception:
        emotion = None
    return ner, emotion


# ─────────────────────────────────────────────────────────────────────────────
# Main parser
# ─────────────────────────────────────────────────────────────────────────────

class NovelTextParser:
    """Parse raw novel text into a ``ParsedNovel`` for video generation.

    The parser is rule-based by default and self-contained. Pass an
    ``llm_provider`` implementing :class:`LLMProvider` to enrich prompts via an
    external model; pass ``use_nlp=True`` (default) to leverage the existing
    ``backend.nlp`` Chinese NLP layer when it is importable.
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        use_nlp: bool = True,
        episode_target_chars: int = EPISODE_TARGET_CHARS,
        scene_target_chars: int = SCENE_TARGET_CHARS,
    ) -> None:
        # Auto-detect best available LLM provider if none specified
        if llm_provider is None:
            llm_provider = get_best_llm_provider()
        self.llm_provider = llm_provider
        self.episode_target_chars = episode_target_chars
        self.scene_target_chars = scene_target_chars
        self._ner, self._emotion = _try_load_nlp() if use_nlp else (None, None)
        # Global character registry: name -> styling description (consistency).
        self._character_registry: dict[str, str] = {}
        if self.llm_provider is not None:
            import logging
            logging.getLogger(__name__).info(
                "Using LLM provider: %s", type(self.llm_provider).__name__
            )

    # ── Public API ──────────────────────────────────────────────────────────

    def parse(self, text: str, title: str = "") -> ParsedNovel:
        """Parse full novel text into a :class:`ParsedNovel`."""
        cleaned = self._normalize_text(text)
        novel_title = title or self._extract_novel_title(cleaned)

        # Build the global character registry up-front so every scene references
        # consistent styling prompts.
        self._character_registry = {}
        self._build_character_registry(cleaned)

        episode_blocks = self._split_episodes(cleaned)

        episodes: list[ParsedEpisode] = []
        for idx, (ep_title, ep_text) in enumerate(episode_blocks, start=1):
            episode = self._parse_episode(ep_text, ep_title, episode_index=idx)
            episodes.append(episode)

        total_duration = sum(ep.total_estimated_duration for ep in episodes)
        return ParsedNovel(
            title=novel_title,
            episodes=episodes,
            characters=dict(self._character_registry),
            total_estimated_duration=round(total_duration, 2),
        )

    def parse_episode(self, text: str, title: str = "", episode_index: int = 1) -> ParsedEpisode:
        """Parse a single episode's text directly."""
        self._character_registry = {}
        self._build_character_registry(text)
        return self._parse_episode(self._normalize_text(text), title, episode_index)

    def extract_characters(self, text: str) -> dict[str, str]:
        """Return a ``{name: styling description}`` mapping for the given text."""
        registry: dict[str, str] = {}
        self._build_character_registry(text, registry)
        return registry

    # ── Episode splitting ───────────────────────────────────────────────────

    def _split_episodes(self, text: str) -> list[tuple[str, str]]:
        """Split novel text into episodes of ~3000-5000 characters.

        Strategy:
        1. Honour explicit chapter headings (第一章, Chapter N, ...). Each
           detected chapter becomes one or more episodes depending on length.
        2. For chapters larger than ``EPISODE_MAX_CHARS``, split on paragraph
           boundaries near the target size.
        3. For unstructured text (no headings), split greedily on paragraph
           boundaries near the target size.
        """
        heading_matches = list(CHAPTER_HEADING.finditer(text))
        blocks: list[tuple[str, str]] = []

        if heading_matches:
            for i, match in enumerate(heading_matches):
                start = match.end()
                end = heading_matches[i + 1].start() if i + 1 < len(heading_matches) else len(text)
                chunk_title = match.group(1).strip()
                chunk_text = text[start:end].strip()
                if chunk_text:
                    blocks.extend(self._size_blocks(chunk_title, chunk_text))
        else:
            blocks.extend(self._size_blocks("", text))

        if not blocks:
            blocks = [("", text)]

        # Final pass: merge tiny trailing/leading blocks (< EPISODE_MIN_CHARS).
        merged: list[tuple[str, str]] = []
        for title, body in blocks:
            if merged and _count_chars(body) < EPISODE_MIN_CHARS:
                prev_title, prev_body = merged[-1]
                merged[-1] = (prev_title, prev_body + "\n" + body)
            else:
                merged.append((title, body))
        return merged

    def _size_blocks(self, title: str, text: str) -> list[tuple[str, str]]:
        """Break an oversized block into episode-sized sub-blocks."""
        body = text.strip()
        if not body:
            return []
        if _count_chars(body) <= EPISODE_MAX_CHARS:
            return [(title or self._fallback_title(body), body)]

        paragraphs = [p.strip() for p in PARAGRAPH_SPLIT.split(body) if p.strip()]
        sub_blocks: list[tuple[str, str]] = []
        current: list[str] = []
        current_len = 0

        for para in paragraphs:
            para_len = _count_chars(para)
            if current and current_len + para_len > EPISODE_MAX_CHARS and current_len >= EPISODE_MIN_CHARS:
                sub_blocks.append((self._sub_title(title, len(sub_blocks) + 1), "\n".join(current)))
                current = [para]
                current_len = para_len
            else:
                current.append(para)
                current_len += para_len
                if current_len >= self.episode_target_chars and para_len >= SCENE_MIN_CHARS:
                    sub_blocks.append((self._sub_title(title, len(sub_blocks) + 1), "\n".join(current)))
                    current = []
                    current_len = 0

        if current:
            tail = "\n".join(current)
            if sub_blocks and _count_chars(tail) < EPISODE_MIN_CHARS:
                prev_title, prev_body = sub_blocks[-1]
                sub_blocks[-1] = (prev_title, prev_body + "\n" + tail)
            else:
                sub_blocks.append((self._sub_title(title, len(sub_blocks) + 1), tail))

        return sub_blocks or [(title or self._fallback_title(body), body)]

    # ── Episode parsing ─────────────────────────────────────────────────────

    def _parse_episode(self, text: str, title: str, episode_index: int) -> ParsedEpisode:
        """Parse one episode into 20-40 scenes with full prompt generation."""
        episode_id = f"ep{episode_index:02d}"
        scene_texts = self._split_scenes(text)
        # Keep each episode within the 20-40 scene window.
        scene_texts = self._fit_scene_count(scene_texts, minimum=20, maximum=40)

        scenes: list[ParsedScene] = []
        for s_idx, scene_text in enumerate(scene_texts, start=1):
            scene_id = f"{episode_id}_s{s_idx:02d}"
            scene = self._build_scene(scene_text, scene_id, episode_id, s_idx)
            scenes.append(scene)

        total_duration = round(sum(s.duration_hint for s in scenes), 2)
        return ParsedEpisode(
            episode_id=episode_id,
            title=title or f"第 {episode_index} 集",
            scenes=scenes,
            total_estimated_duration=total_duration,
        )

    # ── Scene splitting ─────────────────────────────────────────────────────

    def _split_scenes(self, text: str) -> list[str]:
        """Split an episode into ~150-250 character scenes.

        Uses a paragraph-aware rule-based splitter as the primary method. It
        respects paragraph boundaries (preserving per-paragraph shot-type
        granularity) and merges/splits to hit the 150-250 char target reliably.

        The existing ``ChineseSceneParser`` is intentionally NOT used for scene
        splitting: its transition-based scenes are coarser than the 150-250 char
        target and would merge dialogue/action/emotional beats together. The NLP
        layer still contributes via character NER and the emotion mapper.
        """
        return self._rule_based_scene_split(text)

    def _rule_based_scene_split(self, text: str) -> list[str]:
        """Paragraph-aware splitter targeting ``scene_target_chars``.

        * A paragraph already within [SCENE_MIN, SCENE_MAX] becomes its own scene.
        * A paragraph larger than SCENE_MAX is split by sentence boundaries.
        * Paragraphs smaller than SCENE_MIN are accumulated until the target is
          reached, then flushed.
        """
        paragraphs = [p.strip() for p in PARAGRAPH_SPLIT.split(text) if p.strip()]
        scenes: list[str] = []
        current: list[str] = []
        current_len = 0

        def flush_current() -> None:
            nonlocal current, current_len
            if current:
                scenes.append(" ".join(current))
                current = []
                current_len = 0

        for para in paragraphs:
            para_len = _count_chars(para)

            # In-band paragraph -> standalone scene (preserves shot-type flavour).
            if SCENE_MIN_CHARS <= para_len <= SCENE_MAX_CHARS:
                flush_current()
                scenes.append(para)
                continue

            # Oversized paragraph -> sentence-based chunking.
            if para_len > SCENE_MAX_CHARS:
                flush_current()
                scenes.extend(self._split_long_paragraph(para))
                continue

            # Undersized paragraph -> accumulate with neighbours.
            if current and current_len + para_len > SCENE_MAX_CHARS:
                flush_current()
            current.append(para)
            current_len += para_len
            if current_len >= self.scene_target_chars:
                flush_current()

        if current:
            tail = " ".join(current)
            if scenes and _count_chars(tail) < SCENE_MIN_CHARS:
                scenes[-1] = scenes[-1] + " " + tail
            else:
                scenes.append(tail)

        return [s for s in scenes if s.strip()]

    def _split_long_paragraph(self, paragraph: str) -> list[str]:
        """Split an oversized paragraph into ~target-sized sentence chunks."""
        sentences = [s.strip() for s in SENTENCE_SPLIT.split(paragraph) if s.strip()]
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for sent in sentences:
            sent_len = _count_chars(sent)
            if current and current_len + sent_len > SCENE_MAX_CHARS and current_len >= SCENE_MIN_CHARS:
                chunks.append(" ".join(current))
                current = [sent]
                current_len = sent_len
            else:
                current.append(sent)
                current_len += sent_len
                if current_len >= self.scene_target_chars:
                    chunks.append(" ".join(current))
                    current = []
                    current_len = 0

        if current:
            chunks.append(" ".join(current))

        return chunks

    def _fit_scene_count(self, scenes: list[str], minimum: int, maximum: int) -> list[str]:
        """Ensure the scene count for an episode stays within [minimum, maximum]."""
        if not scenes:
            return [""]

        # Too many scenes → evenly subsample.
        if len(scenes) > maximum:
            step = len(scenes) / maximum
            indexes = [int(round(i * step)) for i in range(maximum)]
            indexes = sorted(set(indexes))[:maximum]
            return [scenes[i] for i in indexes]

        # Too few scenes → split the largest ones until we reach the minimum.
        while len(scenes) < minimum:
            # Find the longest scene to split in half.
            longest_idx = max(range(len(scenes)), key=lambda i: _count_chars(scenes[i]))
            longest = scenes[longest_idx]
            if _count_chars(longest) < SCENE_MIN_CHARS * 2:
                break  # nothing left to split meaningfully
            halves = self._split_in_half(longest)
            scenes[longest_idx:longest_idx + 1] = halves

        return scenes

    @staticmethod
    def _split_in_half(text: str) -> list[str]:
        """Split a block into two roughly equal parts on a sentence boundary."""
        sentences = [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]
        if len(sentences) < 2:
            return [text]
        mid = len(sentences) // 2
        return [" ".join(sentences[:mid]), " ".join(sentences[mid:])]

    # ── Scene building ──────────────────────────────────────────────────────

    def _build_scene(
        self,
        scene_text: str,
        scene_id: str,
        episode_id: str,
        scene_index: int,
    ) -> ParsedScene:
        """Assemble a fully-populated :class:`ParsedScene`.

        Following the tutorial's structured format, the scene includes:
        - Shot type and camera movement (镜头类型)
        - Visual description (画面描述) — filmable, concise
        - Character action (角色动作) — what characters are doing
        - Environment detail (环境细节) — location, lighting, weather
        - Narration/dialogue (旁白/对白) — clean text for TTS
        """
        description = scene_text.strip()
        characters = self._detect_scene_characters(scene_text)
        location = self._detect_location(scene_text)
        mood = self._detect_mood(scene_text)
        shot_type = self._classify_shot_type(scene_text, scene_index)
        camera = CAMERA_BY_SHOT_TYPE.get(shot_type, "slow pan across wide scene")
        narration = _clean_narration(scene_text)
        seed = _stable_seed(scene_id)
        duration_hint = DURATION_BY_SHOT_TYPE.get(shot_type, SCENE_TARGET_SECONDS)

        positive_prompt = self._build_positive_prompt(
            description=description,
            characters=characters,
            location=location,
            mood=mood,
            shot_type=shot_type,
        )
        negative_prompt = ANTI_MOSAIC_NEGATIVE

        # Optional LLM enrichment — never fatal.
        # The LLM may return tutorial-specific structured fields that override
        # the rule-based defaults for higher quality output.
        if self.llm_provider is not None:
            overrides = self._llm_enhance(scene_text, {
                "episode_id": episode_id,
                "scene_id": scene_id,
                "characters": characters,
                "location": location,
                "mood": mood,
                "shot_type": shot_type,
                "positive_prompt": positive_prompt,
                "negative_prompt": negative_prompt,
            })
            positive_prompt = overrides.get("positive_prompt", positive_prompt)
            negative_prompt = overrides.get("negative_prompt", negative_prompt)
            shot_type = overrides.get("shot_type", shot_type)
            camera = overrides.get("camera", camera)
            mood = overrides.get("mood", mood)
            location = overrides.get("location", location)
            narration = overrides.get("narration", narration)
            # Use LLM-provided visual description if available (tutorial format)
            if overrides.get("visual_description"):
                description = overrides["visual_description"]
            # Ensure quality boosters are always appended after LLM enhancement
            # (LLM may not include quality keywords in its prompt)
            if positive_prompt and not any(
                qb in positive_prompt.lower()
                for qb in ["8k", "uhd", "detailed", "sharp", "masterpiece"]
            ):
                positive_prompt = f"{positive_prompt}, {QUALITY_BOOSTERS}"

        return ParsedScene(
            scene_id=scene_id,
            episode_id=episode_id,
            description=description,
            characters=characters,
            location=location,
            mood=mood,
            shot_type=shot_type,
            narration=narration,
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            camera=camera,
            seed=seed,
            duration_hint=duration_hint,
        )

    def _llm_enhance(self, scene_text: str, context: dict[str, Any]) -> dict[str, Any]:
        """Call the optional LLM provider, swallowing any error."""
        if self.llm_provider is None:
            return {}
        try:
            result = self.llm_provider.enhance_scene(scene_text, context)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    # ── Shot-type classification ────────────────────────────────────────────

    def _classify_shot_type(self, text: str, scene_index: int) -> str:
        """Classify a scene into one of the six cinematic shot types.

        Priority (most specific first):
        1. The first scene of an episode is always an establishing shot.
        2. Transition markers at the scene start (第二天, 此时, ...).
        3. Action verbs (冲, 拔剑, 斩, ...) — beats over dialogue/emotion.
        4. Emotional keywords (流泪, 绝望, 微笑, ...).
        5. Dialogue cues (说道, 喊道, punctuation 「」“”).
        6. Mid-episode wide establishing descriptors (俯瞰, 全景, ...).
        7. Fallback: narration.
        """
        if scene_index == 1:
            return "establishing"

        transition_kws = SHOT_TYPE_KEYWORDS["transition"]
        if any(text.startswith(kw) or kw in text[:30] for kw in transition_kws):
            return "transition"

        if any(kw in text for kw in SHOT_TYPE_KEYWORDS["action"]):
            return "action"

        if any(kw in text for kw in SHOT_TYPE_KEYWORDS["emotional"]):
            return "emotional"

        if any(kw in text for kw in SHOT_TYPE_KEYWORDS["dialogue"]):
            return "dialogue"
        if any(marker in text for marker in ("「", "」", "“", "”", '"')):
            return "dialogue"

        if any(kw in text for kw in SHOT_TYPE_KEYWORDS["establishing"]):
            return "establishing"

        return "narration"

    # ── Location / mood detection ───────────────────────────────────────────

    def _detect_location(self, text: str) -> str:
        """Return an English setting fragment for the scene's location."""
        for _key, (keywords, en_fragment) in LOCATION_MAP.items():
            if any(kw in text for kw in keywords):
                return en_fragment
        return "unspecified setting, neutral environment"

    def _detect_mood(self, text: str) -> str:
        """Return a mood label (``tense``/``calm``/.../``neutral``)."""
        if self._emotion is not None:
            try:
                analysis = self._emotion.analyze_text(text)
                if analysis["emotions"]:
                    # Use the first detected emotion's keyword to derive a label.
                    return self._emotion_label(analysis["emotions"][0])
            except Exception:
                pass

        scores: dict[str, int] = {}
        for mood, (keywords, _en) in MOOD_MAP.items():
            scores[mood] = sum(text.count(kw) for kw in keywords)
        if max(scores.values(), default=0) > 0:
            return max(scores, key=scores.get)
        return "neutral"

    @staticmethod
    def _emotion_label(emotion_entry: dict[str, Any]) -> str:
        """Map an EmotionMapper entry back to a coarse mood label."""
        keyword = emotion_entry.get("keyword", "")
        for mood, (keywords, _en) in MOOD_MAP.items():
            if keyword in keywords:
                return mood
        return "neutral"

    # ── Character extraction ────────────────────────────────────────────────

    def _build_character_registry(
        self,
        text: str,
        registry: Optional[dict[str, str]] = None,
    ) -> None:
        """Populate the global character registry with styling descriptions."""
        target = registry if registry is not None else self._character_registry
        names = self._extract_character_names(text)
        for name in names:
            if name not in target:
                target[name] = self._build_character_description(name, text)

    def _extract_character_names(self, text: str) -> list[str]:
        """Detect character names.

        The rule-based ``surname + action-suffix`` detector is trusted (high
        precision). NER-proposed names are added only when they pass a
        person-context check, so non-person tokens (玉佩, 封印, ...) are rejected.
        """
        rule_names = self._rule_based_name_detection(text)

        ner_names: list[str] = []
        if self._ner is not None and _is_chinese_text(text):
            try:
                ner_names = self._ner.extract_names(text) or []
            except Exception:
                ner_names = []

        validated_ner = [
            n for n in ner_names
            if n not in NAME_STOPWORDS
            and len(n) >= 2
            and n not in rule_names
            and self._has_person_context(n, text)
        ]

        seen: set[str] = set(rule_names)
        merged: list[str] = list(rule_names)
        for name in validated_ner:
            if name not in seen:
                seen.add(name)
                merged.append(name)
        return merged[:20]

    @staticmethod
    def _has_person_context(name: str, text: str) -> bool:
        """A token is likely a person if it appears immediately before a
        speech/action verb (``name + 说/道/看/走...``).

        This is intentionally strict: a frequency-based "surname-led + count"
        fallback was rejected because repeated paragraphs inflate counts and let
        common substrings (苏醒, 何妨, 于点) through as false positives.
        """
        return any(name + suffix in text for suffix in NAME_ACTION_SUFFIXES)

    def _rule_based_name_detection(self, text: str) -> list[str]:
        """Detect names via ``surname + action-suffix`` and frequency patterns.

        Looks for patterns like "张三说", "李四看着", "苏璃冷笑" and ranks
        candidates by frequency. Works without jieba.
        """
        if not _is_chinese_text(text):
            # English fallback: capitalized words.
            caps = re.findall(r"\b([A-Z][a-z]{2,})\b", text)
            stop = {"The", "And", "But", "That", "With", "From", "This", "They"}
            return sorted({c for c in caps if c not in stop})

        surname_class = "[" + COMMON_SURNAMES + "]"
        # surname + 1 or 2 CJK chars, immediately followed by an action suffix.
        # Non-greedy ``{1,2}?`` so "苏璃冷道" captures "苏璃" (not "苏璃冷"): it
        # tries the shorter name first and only extends to 3 chars when the
        # 2-char name is not itself followed by a suffix (e.g. "林轩宇说").
        pattern = re.compile(rf"({surname_class}[\u4e00-\u9fff]{{1,2}}?)(?=[{''.join(NAME_ACTION_SUFFIXES)}])")
        candidates: dict[str, int] = {}
        for match in pattern.finditer(text):
            name = match.group(1)
            if name in NAME_STOPWORDS:
                continue
            candidates[name] = candidates.get(name, 0) + 1

        # Also count standalone mentions of the same candidate to reinforce.
        for name in list(candidates.keys()):
            candidates[name] += text.count(name)

        # Keep names mentioned at least twice, sorted by frequency.
        ranked = sorted(
            (n for n, c in candidates.items() if c >= 2),
            key=lambda n: candidates[n],
            reverse=True,
        )
        return ranked[:20]

    def _detect_scene_characters(self, scene_text: str) -> list[str]:
        """Return the registered characters that appear in this scene."""
        if not self._character_registry:
            return []
        present = [name for name in self._character_registry if name in scene_text]
        return present[:6]

    def _build_character_description(self, name: str, text: str) -> str:
        """Generate a reusable English styling prompt for a character.

        Combines a gender guess, detected appearance keywords and a consistency
        anchor so the same character renders consistently across scenes.
        """
        gender_label = self._guess_gender_label(name, text)
        appearance = self._extract_appearance_hints(name, text)
        role = self._guess_role(name, text)

        parts = [name, gender_label]
        if role:
            parts.append(role)
        if appearance:
            parts.append(appearance)
        # Consistency anchor: stable descriptors so re-generation matches.
        parts.append("consistent appearance, same face, detailed features")
        return ", ".join(p for p in parts if p)

    def _guess_gender_label(self, name: str, text: str) -> str:
        """Heuristic gender guess from pronouns / role words near the name."""
        sentences = re.split(r"[。！？\n]+", text)
        relevant = [s for s in sentences if name in s]
        combined = " ".join(relevant)
        male = sum(combined.count(kw) for kw in GENDER_HINTS["male"][0])
        female = sum(combined.count(kw) for kw in GENDER_HINTS["female"][0])
        if female > male:
            return GENDER_HINTS["female"][1]
        if male > female:
            return GENDER_HINTS["male"][1]
        return "person"

    def _guess_role(self, name: str, text: str) -> str:
        """Coarse role guess for styling flavour."""
        sentences = re.split(r"[。！？\n]+", text)
        relevant = " ".join(s for s in sentences if name in s)
        if any(kw in relevant for kw in ("剑", "刀", "武", "战斗", "拔剑")):
            return "warrior, combat attire"
        if any(kw in relevant for kw in ("法", "咒", "灵", "施法", "凝聚")):
            return "mage, flowing robes, arcane aura"
        if any(kw in relevant for kw in ("王", "皇", "帝", "公主", "公子")):
            return "nobility, refined garments"
        return ""

    def _extract_appearance_hints(self, name: str, text: str) -> str:
        """Mine a few appearance descriptors from sentences mentioning the name."""
        sentences = re.split(r"[。！？\n]+", text)
        relevant = " ".join(s for s in sentences if name in s)

        hints: list[str] = []
        hair_map = {
            "银发": "silver hair", "白发": "white hair", "黑发": "black hair",
            "金发": "blonde hair", "蓝发": "blue hair", "红发": "red hair",
            "长发": "long hair", "短发": "short hair", "马尾": "ponytail",
        }
        for cn, en in hair_map.items():
            if cn in relevant:
                hints.append(en)
                break

        eye_map = {
            "蓝眼": "blue eyes", "金眼": "golden eyes", "红眼": "red eyes",
            "绿眼": "green eyes", "紫眼": "purple eyes", "银眼": "silver eyes",
        }
        for cn, en in eye_map.items():
            if cn in relevant:
                hints.append(en)
                break

        if any(kw in relevant for kw in ("铠甲", "战甲", "甲胄")):
            hints.append("wearing armor")
        elif any(kw in relevant for kw in ("长袍", "道袍", "法袍")):
            hints.append("wearing flowing robes")
        elif any(kw in relevant for kw in ("裙", "纱")):
            hints.append("wearing elegant dress")

        return ", ".join(hints)

    # ── Prompt generation ───────────────────────────────────────────────────

    def _build_positive_prompt(
        self,
        description: str,
        characters: list[str],
        location: str,
        mood: str,
        shot_type: str,
    ) -> str:
        """Assemble the cinematic English positive prompt for a scene.

        Following the tutorial's structured prompt format:
        1. Film style anchor (photorealistic, cinematic lighting, 35mm)
        2. Shot type + camera movement (镜头类型 + 运镜)
        3. Setting / environment detail (环境细节)
        4. Character visual descriptions with consistency (角色视觉描述)
        5. Mood atmosphere (情绪氛围)
        6. Action / visual hints from description (动作/画面)
        7. Quality boosters (画质增强)
        """
        fragments: list[str] = [STYLE_ANCHOR]

        # Shot type + camera movement (tutorial: 镜头类型 + 运镜方向)
        camera = CAMERA_BY_SHOT_TYPE.get(shot_type, "cinematic shot")
        fragments.append(camera)

        # Environment / setting (tutorial: 环境细节)
        fragments.append(location)

        # Character visual descriptions with consistency anchors
        # (tutorial: 角色视觉描述 — appearance, clothing, pose)
        for name in characters[:3]:
            styling = self._character_registry.get(name, name)
            fragments.append(styling)

        # Mood atmosphere (tutorial: 情绪氛围)
        mood_en = self._mood_to_english(mood)
        if mood_en:
            fragments.append(mood_en)

        # Action / visual hints mined from the scene description
        # (tutorial: 画面描述 — filmable action)
        action_hint = self._action_hint(description)
        if action_hint:
            fragments.append(action_hint)

        # Quality boosters (tutorial: 画质增强)
        fragments.append(QUALITY_BOOSTERS)

        # Collapse duplicates while preserving order.
        seen: set[str] = set()
        unique: list[str] = []
        for frag in fragments:
            key = frag.strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(frag)
        return ", ".join(unique)

    def _mood_to_english(self, mood: str) -> str:
        """Map a mood label to its English atmosphere fragment."""
        for _mood, (_keywords, en_fragment) in MOOD_MAP.items():
            if _mood == mood:
                return en_fragment
        return ""

    def _action_hint(self, text: str) -> str:
        """Translate a detected Chinese action verb into an English visual hint."""
        if self._emotion is not None:
            try:
                hints = self._emotion.get_shot_prompt_hints(text)
                if hints:
                    return hints[0]
            except Exception:
                pass

        # Rule-based fallback: first matched action keyword -> English focus.
        action_map: dict[str, str] = {
            "拔剑": "hand on hilt, blade emerging, metallic glint",
            "握拳": "clenched fists, tense posture",
            "流泪": "teardrop tracing cheek, trembling lashes",
            "微笑": "gentle smile, soft expression",
            "怒吼": "mouth wide, throat strained, visible force",
            "冲锋": "forward momentum, dust kicking up",
            "跃起": "figure rising against sky, clothing flowing",
            "凝视": "unblinking eyes, reflected light in pupils",
            "施法": "glowing hands, energy swirling, runes appearing",
            "转身": "body rotating, hair swinging",
        }
        for cn, en in action_map.items():
            if cn in text:
                return en
        return ""

    # ── Title helpers ───────────────────────────────────────────────────────

    def _extract_novel_title(self, text: str) -> str:
        """Use the first chapter heading or the first non-empty line as title."""
        match = CHAPTER_HEADING.search(text)
        if match:
            return match.group(1).strip()[:60]
        for line in text.splitlines():
            line = line.strip()
            if line:
                return line[:60]
        return "未命名小说"

    def _fallback_title(self, text: str) -> str:
        """Title for an unlabelled episode block."""
        return f"片段（{_count_chars(text)}字）"

    def _sub_title(self, base_title: str, part: int) -> str:
        """Title for a sub-episode produced by length-based splitting."""
        if base_title:
            return f"{base_title}（{part}）" if part > 1 else base_title
        return f"片段（第{part}部分）"

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Trim and collapse excessive blank lines while preserving structure."""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        return text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Convenience + integration helpers
# ─────────────────────────────────────────────────────────────────────────────

def parse_novel(text: str, title: str = "", use_nlp: bool = True) -> ParsedNovel:
    """Convenience wrapper: parse novel text with a fresh rule-based parser."""
    return NovelTextParser(use_nlp=use_nlp).parse(text, title=title)


def to_plan_shots(parsed: ParsedNovel) -> list[dict[str, Any]]:
    """Flatten a :class:`ParsedNovel` into shot dicts compatible with the
    existing production pipeline (``ShotSpec``-shaped).

    Each scene becomes one shot. The returned dicts mirror the fields used by
    :class:`backend.production.contracts.ShotSpec` so they can be passed
    straight into ``ProductionPlan`` construction.
    """
    shots: list[dict[str, Any]] = []
    shot_number = 0
    for episode in parsed.episodes:
        for scene in episode.scenes:
            shot_number += 1
            shots.append({
                "id": scene.scene_id,
                "shot_number": shot_number,
                "description": scene.description[:200],
                "duration": scene.duration_hint,
                "camera": scene.camera,
                "characters": list(scene.characters),
                "dialogue": [],
                "sfx": [],
                "positive_prompt": scene.positive_prompt,
                "negative_prompt": scene.negative_prompt,
                "narration": scene.narration,
                "transition": "fade",
                "seed": scene.seed,
            })
    return shots


# ─────────────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover - manual smoke test
    _sample = (
        "第一章 风起\n"
        "苏璃站在悬崖边，银发在风中飞扬。她凝视着远方的城市，蓝眼中倒映着夜空的星光。\n"
        "“又来了。”苏璃低声道，握紧了手中的长剑。\n"
        "突然，一道黑影从天而降。林轩冲了过来，拔剑出鞘，剑身闪烁着寒光。\n"
        "“小心！”林轩喊道，挡在苏璃身前。\n"
        "两人并肩而立，面对着逐渐逼近的妖魔。战斗一触即发，空气中弥漫着紧张的压迫感。\n"
        "苏璃施法凝聚灵力，双手泛起蓝色的光芒。林轩怒吼一声，冲锋向前，挥剑斩下。\n"
        "第二天清晨，阳光洒在废墟之上。苏璃看着满目疮痍，心中涌起一阵悲凉。\n"
        "“结束了么？”她轻声问，泪水在眼眶中打转。\n"
    ) * 6  # repeat to exceed one episode length

    _parsed = parse_novel(_sample, title="风起录")
    print(f"Novel: {_parsed.title}")
    print(f"Episodes: {len(_parsed.episodes)} | Characters: {len(_parsed.characters)}")
    print(f"Total duration: {_parsed.total_estimated_duration}s")
    for ep in _parsed.episodes:
        print(f"  {ep.episode_id} {ep.title}: {len(ep.scenes)} scenes, {ep.total_estimated_duration}s")
        for sc in ep.scenes[:2]:
            print(f"    {sc.scene_id} [{sc.shot_type}/{sc.mood}] chars={sc.characters}")
            print(f"      prompt: {sc.positive_prompt[:120]}...")
            print(f"      narration: {sc.narration}")
