"""
AI Manga Studio Pro V1.0 — AI Director Core

The AI Director is the central intelligence module responsible for:
1. Reading and understanding novel / script content
2. Chapter segmentation
3. Plot decomposition
4. Character extraction and profiling
5. Scene identification and description
6. Shot-by-shot storyboard planning
7. Outputting structured JSON for downstream pipeline consumption
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from backend.models import DirectorParseResult, ShotPlan, ShotType

try:
    from backend.prompt_refiner import LLMClient, CharacterDNA, StyleDNA
    _LLM_AVAILABLE = True
except ImportError:
    _LLM_AVAILABLE = False

# V3.5 Engine imports (lazy-loaded)
_V35_ENGINES: Dict[str, Any] = {}


# ============================================================
# Data Classes
# ============================================================

@dataclass
class CharacterProfile:
    """Internal representation of an extracted character."""
    name: str = ""
    aliases: List[str] = field(default_factory=list)
    gender: str = "unknown"
    estimated_age: int = 0
    role: str = ""  # protagonist / antagonist / supporting
    traits: List[str] = field(default_factory=list)
    appearance_hints: List[str] = field(default_factory=list)
    first_appearance_chapter: int = 0


@dataclass
class SceneInfo:
    """Internal representation of an identified scene."""
    name: str = ""
    location: str = ""
    time_of_day: str = "day"
    weather: str = "clear"
    mood: str = "neutral"
    description: str = ""
    appears_in_chapters: List[int] = field(default_factory=list)


@dataclass
class ShotDirective:
    """A single shot directive emitted by the AI Director."""
    index: int = 0
    chapter_index: int = 0
    shot_type: ShotType = ShotType.medium
    camera: str = ""
    characters_present: List[str] = field(default_factory=list)
    scene_name: str = ""
    dialogue: str = ""
    narration: str = ""
    action: str = ""
    emotion: str = ""
    raw_prompt_hint: str = ""


# ============================================================
# Multi-Agent Architecture (LLM-driven)
# ============================================================

class NovelTextLeakError(Exception):
    """Raised when raw novel text leaks into a layer that must only
    receive structured JSON input. This is a security boundary violation."""


class CharacterAgent:
    """LLM-driven character analysis agent.

    Analyzes characters for visual consistency: appearance, personality,
    relationships, and growth arc. Outputs CharacterDNA for downstream
    prompt generation.
    """

    _SYSTEM_PROMPT = (
        "你是一位专业的角色设计师和视觉设定专家。"
        "请根据小说文本，深入分析每个角色的视觉特征。\n"
        "要求：\n"
        "1. 详细描述外貌（发型/发色/瞳色/体型/服装风格）\n"
        "2. 推断性格特质和气质\n"
        "3. 分析角色之间的关系动态\n"
        "4. 描述角色成长弧线（如何变化）\n"
        "输出 JSON 格式："
        '{{"characters":[{{"name":"...","gender":"...","estimated_age":18,'
        '"hair_style":"...","hair_color":"...","eye_color":"...",'
        '"body_type":"...","clothing":"...","personality":["..."],'
        '"arc":"...","relationships":[{{"with":"...","type":"..."}}]}}]}}'
    )

    def __init__(self, client: "LLMClient") -> None:
        self._client = client

    def analyze(self, novel_text: str) -> List[Dict[str, Any]]:
        """Analyze novel text and return character profiles."""
        try:
            response = self._client.chat(
                messages=[
                    {"role": "system", "content": self._SYSTEM_PROMPT},
                    {"role": "user", "content": f"分析以下小说中的角色：\n\n{novel_text[:8000]}"},
                ],
                temperature=0.5,
                max_tokens=2000,
            )
            data = json.loads(response)
            return data.get("characters", [])
        except Exception as e:
            logger.warning(f"CharacterAgent LLM failure, will fallback to rules: {e}")
            return []

    def to_character_profiles(self, llm_output: List[Dict[str, Any]]) -> List["CharacterProfile"]:
        """Convert LLM output to CharacterProfile list."""
        profiles = []
        for item in llm_output:
            profiles.append(CharacterProfile(
                name=item.get("name", "Unknown"),
                gender=item.get("gender", "unknown"),
                estimated_age=item.get("estimated_age", 20),
                role=item.get("role", "supporting"),
                traits=item.get("personality", []),
                appearance_hints=[
                    item.get("hair_style", ""),
                    item.get("hair_color", ""),
                    item.get("eye_color", ""),
                    item.get("body_type", ""),
                    item.get("clothing", ""),
                ],
            ))
        return profiles


class SceneAgent:
    """LLM-driven scene analysis agent.

    Analyzes scenes for architectural style, weather, time of day,
    mood, and color palette. Outputs SceneDNA for background generation.
    """

    _SYSTEM_PROMPT = (
        "你是一位专业的场景概念设计师。"
        "请根据小说文本，识别并描述所有场景的视觉特征。\n"
        "要求：\n"
        "1. 描述建筑/环境风格\n"
        "2. 推断时间（日/夜/黄昏）和天气\n"
        "3. 分析氛围和色调（暖/冷/中性）\n"
        "4. 给出 Color Palette（3-5个颜色）\n"
        "输出 JSON 格式："
        '{{"scenes":[{{"name":"...","location":"...","style":"...",'
        '"time_of_day":"...","weather":"...","mood":"...",'
        '"color_palette":["#hex","..."],"description":"..."}}]}}'
    )

    def __init__(self, client: "LLMClient") -> None:
        self._client = client

    def analyze(self, novel_text: str) -> List[Dict[str, Any]]:
        """Analyze novel text and return scene descriptions."""
        try:
            response = self._client.chat(
                messages=[
                    {"role": "system", "content": self._SYSTEM_PROMPT},
                    {"role": "user", "content": f"分析以下小说中的场景：\n\n{novel_text[:8000]}"},
                ],
                temperature=0.5,
                max_tokens=2000,
            )
            data = json.loads(response)
            return data.get("scenes", [])
        except Exception as e:
            logger.warning(f"SceneAgent LLM failure, will fallback to rules: {e}")
            return []

    def to_scene_infos(self, llm_output: List[Dict[str, Any]]) -> List["SceneInfo"]:
        """Convert LLM output to SceneInfo list."""
        scenes = []
        for item in llm_output:
            scenes.append(SceneInfo(
                name=item.get("name", "Unknown"),
                location=item.get("location", ""),
                time_of_day=item.get("time_of_day", "day"),
                weather=item.get("weather", "clear"),
                mood=item.get("mood", "neutral"),
                description=item.get("description", ""),
            ))
        return scenes


class StoryAgent:
    """LLM-driven story analysis agent.

    Analyzes chapter pacing, conflict rhythm, plot twists, and shot
    rhythm planning. Outputs a shot plan table.
    """

    _SYSTEM_PROMPT = (
        "你是一位专业的漫画分镜师和故事节奏顾问。"
        "请根据小说章节内容，规划分镜计划。\n"
        "要求：\n"
        "1. 评估章节节奏（快/慢/紧张/舒缓）\n"
        "2. 识别关键冲突和转折点\n"
        "3. 规划分镜节奏：每章建议 shot 数量、镜头时长、机位切换频率\n"
        "输出 JSON 格式："
        '{{"chapters":[{{"index":1,"pacing":"...","conflict":"...","twist":"...",'
        '"recommended_shots":12,"avg_shot_duration":3.5,"camera_rhythm":"..."}}]}}'
    )

    def __init__(self, client: "LLMClient") -> None:
        self._client = client

    def analyze(self, chapters: List[str]) -> List[Dict[str, Any]]:
        """Analyze chapters and return shot plan."""
        summaries = "\n\n".join(
            f"[Chapter {i+1}]\n{ch[:500]}..." for i, ch in enumerate(chapters[:10])
        )
        try:
            response = self._client.chat(
                messages=[
                    {"role": "system", "content": self._SYSTEM_PROMPT},
                    {"role": "user", "content": f"分析以下小说的章节结构：\n\n{summaries}"},
                ],
                temperature=0.5,
                max_tokens=2000,
            )
            data = json.loads(response)
            return data.get("chapters", [])
        except Exception as e:
            logger.warning(f"StoryAgent LLM failure, will fallback to rules: {e}")
            return []


# ============================================================
# V2.0 Three-Role Director Dispatch
# ============================================================

class QwenDirector:
    """Layer 1 — Story Director (Qwen3 235B).

    Reads the raw novel text, understands the plot, segments
    chapters, and identifies emotional arcs.

    THIS IS THE ONLY agent that directly sees the novel text.
    All downstream agents receive structured JSON only.
    """

    def __init__(self, client: "LLMClient") -> None:
        self._client = client
        self._endpoint = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self._model = "qwen3-235b-a22b"

    def analyze_novel(self, novel_text: str) -> Dict[str, Any]:
        """Read novel text and output structured chapter analysis.

        Args:
            novel_text: The full novel text (only this layer touches raw text).

        Returns:
            Dict with keys: chapters, emotional_arc, key_characters, key_scenes.
        """
        _SYSTEM = (
            "你是一位AI漫剧主导演（Story Director）。"
            "请阅读小说全文，理解剧情后输出结构化分析。\n"
            "要求：\n"
            "1. 按剧情自然分章（每章约800-1200字为宜），给出每章标题和摘要\n"
            "2. 绘制整体情绪曲线（每章的情绪基调：紧张/舒缓/悲伤/激昂/悬疑）\n"
            "3. 列出关键角色（名字+一句话描述）\n"
            "4. 列出关键场景（地点+氛围）\n"
            "输出 JSON 格式："
            '{{"chapters":[{{"index":1,"title":"...",'
            '"summary":"...","emotion":"...","word_count":0}}],'
            '"emotional_arc":["...","..."],'
            '"key_characters":[{{"name":"...","desc":"..."}}],'
            '"key_scenes":[{{"location":"...","atmosphere":"..."}}]}}'
        )

        try:
            response = self._client.chat(
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": f"分析以下小说：\n\n{novel_text[:12000]}"},
                ],
                temperature=0.4,
                max_tokens=3000,
                endpoint=self._endpoint,
                model=self._model,
            )
            return json.loads(response)
        except Exception as e:
            logger.warning(f"QwenDirector (Qwen3-235B) failed: {e}")
            return {}


class DeepSeekPlanner:
    """Layer 1 — Shot Planner (DeepSeek R1).

    Receives structured chapter analysis from QwenDirector and plans
    the shot-by-shot storyboard: shot count, camera positions,
    pacing, transitions.

    NEVER sees raw novel text — only structured JSON.
    """

    def __init__(self, client: "LLMClient") -> None:
        self._client = client
        self._endpoint = "https://api.deepseek.com/v1"
        self._model = "deepseek-reasoner"

    def plan_shots(self, chapter_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Plan shots from structured chapter analysis.

        Args:
            chapter_analysis: Output from QwenDirector.analyze_novel().
                Must be a dict — raw novel text triggers NovelTextLeakError.

        Returns:
            List of shot dicts with shot_type/camera/characters/scene/dialogue/...
        """
        self._assert_structured(chapter_analysis)

        _SYSTEM = (
            "你是一位AI漫画分镜师（Shot Planner）。"
            "请根据剧情分析结果，规划每个镜头的拍摄方案。\n"
            "要求：\n"
            "1. 每章规划 8-15 个镜头\n"
            "2. 每个镜头指定：shot_type(close_up/medium/full_body/wide/dutch/"
            "over_shoulder/low_angle/high_angle/pov)、camera描述、在场角色、"
            "场景、对话（如有）、动作描述、情绪基调、narration\n"
            "3. 注意镜头节奏：紧张时短镜头快切，抒情时长镜头渐进\n"
            "4. 标注转场方式（cut/fade/dissolve/wipe）\n"
            "输出 JSON 格式："
            '{{"shots":[{{"chapter":1,"index":1,"shot_type":"medium",'
            '"camera":"eye level, slightly panning right","characters":["主角"],'
            '"scene":"教室","dialogue":"","action":"推门走进教室",'
            '"emotion":"neutral","narration":"新学期的第一天","transition":"cut"}}]}}'
        )

        try:
            analysis_str = json.dumps(chapter_analysis, ensure_ascii=False)
            response = self._client.chat(
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": f"根据以下剧情分析规划镜头：\n\n{analysis_str[:10000]}"},
                ],
                temperature=0.3,
                max_tokens=4000,
                endpoint=self._endpoint,
                model=self._model,
            )
            data = json.loads(response)
            return data.get("shots", [])
        except Exception as e:
            logger.warning(f"DeepSeekPlanner (DeepSeek R1) failed: {e}")
            return []

    @staticmethod
    def _assert_structured(data: Any) -> None:
        """Guard: ensure input is structured dict, not raw novel text."""
        if isinstance(data, str):
            raise NovelTextLeakError(
                "DeepSeekPlanner received raw string — expected structured dict "
                "from QwenDirector. Raw novel text must not cross this boundary."
            )
        if not isinstance(data, dict):
            raise NovelTextLeakError(
                f"DeepSeekPlanner received {type(data).__name__} — "
                "expected structured dict from QwenDirector."
            )


class LocalDirector:
    """Layer 1 fallback — Local Qwen3 32B.

    Runs locally via Ollama when remote APIs are unavailable.
    Combines story understanding + shot planning in one pass
    (reduced capability but ensures pipeline doesn't stall).
    """

    def __init__(self, client: "LLMClient") -> None:
        self._client = client
        self._endpoint = "http://localhost:11434/v1"
        self._model = "qwen3:32b"

    def run(self, novel_text: str) -> Dict[str, Any]:
        """One-pass analysis: chapters + shots from raw novel text.

        Only used as fallback when QwenDirector + DeepSeekPlanner
        are both unavailable.
        """
        _SYSTEM = (
            "你是一位AI漫剧导演。请阅读小说，完成：\n"
            "1. 分章并分析剧情\n"
            "2. 为每章规划镜头（8-15个/章）\n"
            "输出 JSON："
            '{{"chapters":[...],"shots":[...]}}'
        )

        try:
            response = self._client.chat(
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": f"分析并规划镜头：\n\n{novel_text[:8000]}"},
                ],
                temperature=0.5,
                max_tokens=3000,
                endpoint=self._endpoint,
                model=self._model,
            )
            return json.loads(response)
        except Exception as e:
            logger.warning(f"LocalDirector (Qwen3-32B local) failed: {e}")
            return {}


# ============================================================
# AI Director Engine
# ============================================================

class AIDirector:
    """Central AI Director that transforms a novel into a shot-by-shot
    storyboard plan for automated manga video generation.

    Attributes:
        novel_path: Path to the source novel file.
        novel_text: Full text content of the novel.
        chapters: Segmented chapters.
        characters: Extracted character profiles.
        scenes: Identified scene locations.
        shots: Planned shot directives.
    """

    # Chapter boundary markers
    CHAPTER_PATTERNS: List[re.Pattern] = [
        re.compile(r"📍\s*第\s*\d+\s*集\s*[^\n]*", re.UNICODE),         # 📍第1集 ...
        re.compile(r"第[一二三四五六七八九十百千\d]+[章节集]\s*[^\n]*", re.UNICODE),
        re.compile(r"Chapter\s+\d+", re.IGNORECASE),
        re.compile(r"^\s*[#＃]\s*\d+", re.MULTILINE),
        re.compile(r"\n{2,}(?=第[一二三四五六七八九十百千\d]+章)", re.UNICODE),
    ]

    # Dialogue detection (supports 「」『』"" smart-quotes)
    DIALOGUE_PATTERN = re.compile(r"[「『""\u201c]([^」』""\u201d]+)[」』""\u201d]")

    # Top 100 Chinese surnames for prose novel character extraction
    CHINESE_SURNAMES: str = (
        "王李张刘陈杨黄赵周吴徐孙马胡朱郭何罗高林梁郑谢宋唐许邓冯韩曹曾彭萧"
        "潘田董袁于叶蒋杜苏魏薛丁沈范江傅钟卢汪戴崔任陆廖姚方金邱夏谭韦贾邹"
        "石熊孟秦阎侯白龙段雷钱汤尹易常武乔贺赖龚文关褚姜古姚"
    )

    # Prose novel: dialogue attribution patterns (supports both before/after dialogue)
    PROSE_ATTR_PATTERNS: List[re.Pattern] = [
        # "dialogue"，某某说/道/问...
        re.compile(r'["\u201d](?:[，,])?\s*([\u4e00-\u9fff]{2,4})'
                   r'(?:柔声|冷声|低声|小声|大声|轻声|怒声|沉声)?'
                   r'(?:说|道|问|开口|冷哼|喊道|骂道|安慰|打断|附和|提醒)'),
        # 某某说/道/问："dialogue"
        re.compile(r'([\u4e00-\u9fff]{2,4})'
                   r'(?:柔声|冷声|低声|小声|大声)?'
                   r'(?:说|道|问|开口|冷哼|喊道|骂道|安慰|打断|提问|开口问道|说道)'
                   r'[：:,，]?\s*["\u201c]'),
        # 某某做动作，"dialogue"
        re.compile(r'([\u4e00-\u9fff]{2,4})'
                   r'(?:看|见|听|走|站|坐|拿|放|转身|回头|抬头|低头|上前|拉住|接过|推开|挡在|冷笑|皱眉|摇头|点头|站起身)'
                   r'[^，。]{0,20}["\u201c]'),
    ]

    # Surname-based name pattern: Surname(1) + given name(1-2 chars)
    SURNAME_NAME_PATTERN: str = (
        r'([%s][\u4e00-\u9fff]{1,2})' % CHINESE_SURNAMES
    )

    # Common non-name words for filtering false positives
    NON_NAME_WORDS: set = {
        "可以", "已经", "没有", "自己", "他们", "我们", "这个", "那个", "什么",
        "不过", "不是", "还是", "只是", "但是", "因为", "所以", "如果", "虽然",
        "一定", "一下", "一起", "一样", "一点", "也是", "就是", "还有", "不会",
        "出来", "起来", "看到", "知道", "觉得", "说道", "问道", "听到", "想到",
        "到了", "这里", "那里", "她的", "他的", "你的", "我的", "看着", "想着",
        "说着", "拿着", "以为", "发现", "忽然", "突然", "并未", "似乎", "已经",
        "出了", "开了", "入了", "进了", "走了", "上了", "也能", "也要", "也会",
        "还能", "还要", "又是", "还没", "整个", "两个", "三个", "几个", "一片",
        "一切", "一边", "一面", "居然", "当然", "果然", "竟然", "自然", "不再",
        "不如", "不能", "如何", "何必", "何况", "这可", "那是", "真是", "总是",
        "确实", "肯定", "完全", "简直", "几乎", "刚才", "曾经", "怎么办",
        "什么事", "一个人", "怎么回事", "没想到", "忍不住", "笑了笑", "下意识",
        "高考刚", "行李箱", "关系",
        # Family/group terms (not individual names)
        "姜家人", "关家人", "姜海集", "姜家", "关家的", "关家", "关家养",
        "关家给", "关家一", "关家四", "关家算", "关家是", "关家花", "关家头",
        "姜家的", "姜家四", "姜家几", "姜家其", "姜家阳", "姜家正",
        "姜老夫", "姜老爷",
        # False positive fragments
        "张口却", "张口", "金光", "金光闪", "高考刚", "行李箱", "李箱便",
        "关父和", "关父这", "关父之", "关父沉",
        "褚姓和", "褚氏当", "褚家就",
        "姜姓", "有关", "关乎",
        "雷刚的",
    }

    # Suffixes that indicate non-person entity (family, company, etc.)
    NON_PERSON_SUFFIXES: tuple = ("家", "家人", "家的", "氏", "姓", "集团", "集")

    def __init__(self, use_llm_agents: bool = False) -> None:
        self.novel_path: Optional[Path] = None
        self.novel_text: str = ""
        self.chapters: List[str] = []
        self.characters: List[CharacterProfile] = []
        self.scenes: List[SceneInfo] = []
        self.shots: List[ShotDirective] = []

        # Multi-Agent legacy setup
        self._use_llm = use_llm_agents
        self._llm_client = None
        self._character_agent: Optional[CharacterAgent] = None
        self._scene_agent: Optional[SceneAgent] = None
        self._story_agent: Optional[StoryAgent] = None

        # V2.0 three-role dispatch
        self._qwen_director: Optional[QwenDirector] = None
        self._deepseek_planner: Optional[DeepSeekPlanner] = None
        self._local_director: Optional[LocalDirector] = None
        self._use_three_role = False

        # V3.5 Engine initialization (lazy)
        self._v35_storyboard: Any = None
        self._v35_camera: Any = None
        self._v35_motion: Any = None
        self._v35_char_reasoner: Any = None
        self._v35_scene_reasoner: Any = None
        self._v35_img_builder: Any = None
        self._v35_video_builder: Any = None
        self._v35_dialogue_opt: Any = None
        self._v35_enabled: bool = False

        if use_llm_agents and _LLM_AVAILABLE:
            try:
                from backend.prompt_refiner import LLMClient
                self._llm_client = LLMClient()

                # Initialize three-role dispatch (V2)
                self._qwen_director = QwenDirector(self._llm_client)
                self._deepseek_planner = DeepSeekPlanner(self._llm_client)
                self._local_director = LocalDirector(self._llm_client)
                self._use_three_role = True

                # Legacy agents (backward compat)
                self._character_agent = CharacterAgent(self._llm_client)
                self._scene_agent = SceneAgent(self._llm_client)
                self._story_agent = StoryAgent(self._llm_client)
                logger.info("AI Director: Three-Role LLM dispatch enabled "
                            "(QwenDirector → DeepSeekPlanner [+ LocalDirector fallback])")
            except Exception as e:
                logger.warning(f"AI Director: LLM agent init failed ({e}), "
                               f"falling back to rule-based mode")
                self._use_llm = False
                self._use_three_role = False

    # ----------------------------------------------------------
    # Phase 1: Load & Segment
    # ----------------------------------------------------------

    def load_novel(self, novel_path: str) -> str:
        """Load novel text from file.

        Args:
            novel_path: Absolute path to the novel file (.txt).

        Returns:
            Full text content of the novel.
        """
        self.novel_path = Path(novel_path)
        logger.info(f"AI Director: Loading novel from {self.novel_path}")

        with open(self.novel_path, "r", encoding="utf-8") as f:
            self.novel_text = f.read()

        logger.info(f"AI Director: Loaded {len(self.novel_text)} characters")
        return self.novel_text

    def segment_chapters(self) -> List[str]:
        """Segment the novel text into individual chapters.

        Uses regex patterns to detect chapter boundaries and splits
        the text accordingly.

        Returns:
            List of chapter texts.
        """
        logger.info("AI Director: Segmenting chapters ...")

        if not self.novel_text:
            return []

        # Try each pattern to find chapter splits
        splits: List[int] = [0]

        for pattern in self.CHAPTER_PATTERNS:
            matches = list(pattern.finditer(self.novel_text))
            if len(matches) >= 2:
                splits = [0] + [m.start() for m in matches]
                break

        if len(splits) <= 1:
            # No chapters found — treat the whole text as one chapter
            self.chapters = [self.novel_text]
            logger.warning("AI Director: No chapter boundaries detected, treating as single chapter")
        else:
            # Discard pre-content before the first chapter (synopsis, title, etc.)
            self.chapters = []
            for i in range(len(splits)):
                start = splits[i]
                end = splits[i + 1] if i + 1 < len(splits) else len(self.novel_text)
                chapter_text = self.novel_text[start:end].strip()
                if chapter_text:
                    self.chapters.append(chapter_text)

            # Skip first split if it's pre-content (before 第1章 / Chapter 1)
            if len(self.chapters) >= 2:
                first_chapter = self.chapters[0]
                # If first "chapter" doesn't look like a real chapter, remove it
                has_chapter_marker = any(
                    p.search(first_chapter[:100]) for p in self.CHAPTER_PATTERNS
                )
                if not has_chapter_marker and len(first_chapter) < 500:
                    logger.info(
                        f"AI Director: Skipping pre-content ({len(first_chapter)} chars)"
                    )
                    self.chapters = self.chapters[1:]

        # Filter empty
        self.chapters = [ch for ch in self.chapters if ch]
        logger.info(f"AI Director: Found {len(self.chapters)} chapters")
        return self.chapters

    # ----------------------------------------------------------
    # Phase 2: Character Extraction
    # ----------------------------------------------------------

    def extract_characters(self) -> List[CharacterProfile]:
        """Extract character profiles from the novel text.

        When LLM agents are enabled, uses CharacterAgent for deep semantic
        analysis. Falls back to multi-strategy rule extraction otherwise.

        Multi-strategy extraction (rule-based):
          1. Structured script: 「Name」说 / 《Name》 patterns
          2. Prose novel: dialogue attribution patterns ("Name说", 某某说:)
          3. Surname-based frequency scan (fallback for all formats)

        Returns:
            List of CharacterProfile objects.
        """
        logger.info("AI Director: Extracting characters ...")

        # Try LLM agent first
        if self._use_llm and self._character_agent:
            llm_chars = self._character_agent.analyze(self.novel_text)
            if llm_chars:
                self.characters = self._character_agent.to_character_profiles(llm_chars)
                logger.info(f"AI Director: [LLM] Extracted {len(self.characters)} characters")
                return self.characters

        # Rule-based fallback (original multi-strategy logic)
        name_candidates: Dict[str, int] = {}

        # --- Strategy 1: Structured script patterns (original) ---
        dialogue_attr = re.findall(
            r"[「『]([^」』]{1,20})[」』]\s*(?:说|道|問|答|喊|叫|嘆|笑|哭)",
            self.novel_text,
        )
        for name in dialogue_attr:
            name_candidates[name.strip()] = name_candidates.get(name.strip(), 0) + 1

        bracket_names = re.findall(r"《([^》]{1,10})》", self.novel_text)
        for name in bracket_names:
            name_candidates[name.strip()] = name_candidates.get(name.strip(), 0) + 1

        # --- Strategy 2: Prose novel dialogue attribution ---
        for pattern in self.PROSE_ATTR_PATTERNS:
            for name in pattern.findall(self.novel_text):
                if name not in self.NON_NAME_WORDS and len(name) >= 2:
                    name_candidates[name] = name_candidates.get(name, 0) + 2

        # --- Strategy 3: Surname-based frequency scan ---
        surname_pat = re.compile(self.SURNAME_NAME_PATTERN)
        for m in surname_pat.finditer(self.novel_text):
            name = m.group()
            if name not in self.NON_NAME_WORDS and len(name) >= 2:
                # Filter out non-person suffixes (家, 家人, 集团, etc.)
                if not name.endswith(self.NON_PERSON_SUFFIXES):
                    name_candidates[name] = name_candidates.get(name, 0) + 1

        # Filter and rank
        sorted_names = sorted(name_candidates.items(), key=lambda x: -x[1])
        self.characters = []

        for idx, (name, count) in enumerate(sorted_names[:25]):
            if count < 3:
                continue
            profile = CharacterProfile(
                name=name,
                aliases=self._find_aliases(name),
                role=self._infer_role(name, idx),
                traits=self._extract_traits(name),
                appearance_hints=self._extract_appearance(name),
                first_appearance_chapter=self._find_first_appearance(name),
            )
            self.characters.append(profile)

        logger.info(f"AI Director: Extracted {len(self.characters)} characters")
        return self.characters

    def _find_aliases(self, name: str) -> List[str]:
        """Find alternate names / nicknames for a character.

        Scans the text for given-name-only references (e.g., "栩栩" for "关栩栩")
        and common Chinese nickname patterns.
        """
        aliases: List[str] = []
        if len(name) < 2:
            return aliases

        # Given name only (e.g., 栩栩 from 关栩栩)
        if len(name) >= 3:
            given_name = name[1:]  # strip surname
            if given_name in self.novel_text:
                aliases.append(given_name)

        # Common Chinese nickname pattern: 小X, 阿X, X儿
        last_char = name[-1]
        for prefix in ["小", "阿"]:
            candidate = f"{prefix}{last_char}"
            if candidate in self.novel_text:
                aliases.append(candidate)
        candidate = f"{last_char}儿"
        if candidate in self.novel_text:
            aliases.append(candidate)

        return aliases

    def _infer_role(self, name: str, index: int) -> str:
        """Heuristically infer character role (protagonist / antagonist / supporting)."""
        if index == 0:
            # Most mentioned character → likely protagonist
            return "protagonist"
        elif index <= 2:
            return "supporting"
        return "supporting"

    def _extract_traits(self, name: str) -> List[str]:
        """Extract personality traits from context around character mentions."""
        traits: List[str] = []
        # Look for common trait words near the character name
        trait_keywords = [
            "勇敢", "善良", "冷酷", "温柔", "暴躁", "聪明", "狡猾",
            "坚强", "懦弱", "正直", "邪恶", "幽默", "沉默",
        ]
        for keyword in trait_keywords:
            # Search within 200 chars of a name mention
            for match in re.finditer(re.escape(name), self.novel_text):
                start = max(0, match.start() - 200)
                end = min(len(self.novel_text), match.end() + 200)
                if keyword in self.novel_text[start:end]:
                    traits.append(keyword)
                    break
        return list(set(traits))

    def _extract_appearance(self, name: str) -> List[str]:
        """Extract appearance description hints."""
        hints: List[str] = []
        appearance_terms = [
            "长发", "短发", "黑发", "白发", "金发", "红发",
            "高挑", "矮小", "瘦削", "魁梧", "英俊", "美丽",
            "眼镜", "伤疤", "纹身",
        ]
        for term in appearance_terms:
            for match in re.finditer(re.escape(name), self.novel_text):
                start = max(0, match.start() - 300)
                end = min(len(self.novel_text), match.end() + 300)
                if term in self.novel_text[start:end]:
                    hints.append(term)
                    break
        return list(set(hints))

    def _find_first_appearance(self, name: str) -> int:
        """Find which chapter the character first appears in."""
        for i, chapter_text in enumerate(self.chapters):
            if name in chapter_text:
                return i + 1
        return 0

    # ----------------------------------------------------------
    # Phase 3: Scene Identification
    # ----------------------------------------------------------

    def identify_scenes(self) -> List[SceneInfo]:
        """Identify distinct scene locations from the novel.

        When LLM agents are enabled, uses SceneAgent for deep semantic
        analysis. Falls back to keyword matching otherwise.

        Returns:
            List of SceneInfo objects.
        """
        logger.info("AI Director: Identifying scenes ...")

        # Try LLM agent first
        if self._use_llm and self._scene_agent:
            llm_scenes = self._scene_agent.analyze(self.novel_text)
            if llm_scenes:
                self.scenes = self._scene_agent.to_scene_infos(llm_scenes)
                logger.info(f"AI Director: [LLM] Identified {len(self.scenes)} scenes")
                return self.scenes

        # Rule-based fallback (keyword matching)
        location_keywords = [
            # Indoor
            ("宫殿", "palace"), ("客厅", "living room"), ("卧室", "bedroom"),
            ("厨房", "kitchen"), ("教室", "classroom"), ("办公室", "office"),
            ("医院", "hospital"), ("酒馆", "tavern"), ("监狱", "prison"),
            ("地下室", "basement"), ("图书馆", "library"), ("实验室", "lab"),
            ("别墅", "villa"), ("别墅大门", "villa gate"), ("病房", "ward"),
            ("书房", "study"), ("走廊", "corridor"), ("楼梯", "stairs"),
            ("阳台", "balcony"), ("酒店", "hotel"), ("餐厅", "restaurant"),
            ("会议室", "conference room"), ("大厅", "hall"),
            # Outdoor
            ("森林", "forest"), ("山顶", "mountain top"), ("海边", "seaside"),
            ("街道", "street"), ("广场", "square"), ("花园", "garden"),
            ("沙漠", "desert"), ("战场", "battlefield"), ("废墟", "ruins"),
            ("天空", "sky"), ("洞穴", "cave"), ("河流", "river"),
            ("公路", "highway"), ("公园", "park"), ("校园", "campus"),
            ("机场", "airport"), ("车站", "station"), ("码头", "dock"),
            # Special
            ("梦境", "dream"), ("异世界", "another world"), ("太空", "space"),
        ]

        found_scenes: Dict[str, int] = {}
        for keyword, en_name in location_keywords:
            count = self.novel_text.count(keyword)
            # Lower threshold to 1 to capture more scenes
            if count >= 1:
                found_scenes[keyword] = count

        self.scenes = []
        for idx, (keyword, count) in enumerate(
            sorted(found_scenes.items(), key=lambda x: -x[1])[:15]
        ):
            scene = SceneInfo(
                name=keyword,
                location=keyword,
                time_of_day=self._infer_time_of_day(keyword),
                weather=self._infer_weather(keyword),
                mood=self._infer_mood(keyword),
                description=f"Scene: {keyword} (mentioned {count} times)",
            )
            self.scenes.append(scene)

        logger.info(f"AI Director: Identified {len(self.scenes)} scenes")
        return self.scenes

    def _infer_time_of_day(self, location: str) -> str:
        """Infer time of day from context."""
        if location in ("宫殿", "卧室", "地下室"):
            return "night"
        if location in ("教室", "办公室", "广场"):
            return "day"
        return "day"

    def _infer_weather(self, location: str) -> str:
        """Infer weather from context."""
        if location in ("沙漠", "战场"):
            return "sunny"
        if location in ("森林", "洞穴"):
            return "overcast"
        return "clear"

    def _infer_mood(self, location: str) -> str:
        """Infer mood / atmosphere."""
        mood_map = {
            "宫殿": "majestic",
            "森林": "mysterious",
            "战场": "tense",
            "花园": "peaceful",
            "废墟": "melancholic",
            "梦境": "surreal",
            "监狱": "oppressive",
        }
        return mood_map.get(location, "neutral")

    # ----------------------------------------------------------
    # Phase 4: Shot Planning
    # ----------------------------------------------------------

    def plan_shots(self) -> List[ShotDirective]:
        """Decompose each chapter into shot-by-shot storyboard.

        Each paragraph becomes ~1 shot, with camera type and
        character presence inferred. Uses last-speaker tracking
        for unattributed dialogue lines.

        Returns:
            List of ShotDirective objects.
        """
        logger.info("AI Director: Planning shots ...")

        self.shots = []
        global_index = 0
        last_speaker: Optional[str] = None

        for chapter_idx, chapter_text in enumerate(self.chapters):
            paragraphs: List[str] = self._split_paragraphs(chapter_text)
            last_speaker = None  # Reset per chapter

            for para_idx, paragraph in enumerate(paragraphs):
                if len(paragraph.strip()) < 10:
                    continue  # skip very short paragraphs

                shot = self._plan_single_shot(
                    global_index=global_index,
                    chapter_index=chapter_idx + 1,
                    paragraph=paragraph,
                )

                # Track last known speaker from this paragraph
                if shot.characters_present:
                    last_speaker = shot.characters_present[0]
                elif shot.dialogue and last_speaker:
                    # Unattributed dialogue: use last known speaker
                    shot.characters_present = [last_speaker]

                self.shots.append(shot)
                global_index += 1

            logger.debug(
                f"Chapter {chapter_idx + 1}: planned {len(paragraphs)} shots"
            )

        logger.info(f"AI Director: Planned {len(self.shots)} total shots")
        return self.shots

    def get_all_characters(self) -> List[Dict[str, str]]:
        """Export all extracted characters for injection into CharacterMemory.

        Collects unique characters from all chapters with inferred
        attributes (hair color, eye color, body type from context).
        The Scheduler feeds these into StabilityManager.

        Returns:
            List of dicts with character attributes.
        """
        all_chars: Dict[str, Dict[str, Any]] = {}

        for chapter_idx, chapter_text in enumerate(self.chapters):
            chars = self.extract_characters(chapter_text, chapter_idx + 1)
            for char in chars:
                name = char.get("name", "")
                if name and name not in all_chars:
                    all_chars[name] = {
                        "name": name,
                        "hair_color": char.get("hair_color", "unknown"),
                        "eye_color": char.get("eye_color", "unknown"),
                        "body_type": char.get("body_type", "unknown"),
                        "hair_style": char.get("hair_style", "unknown"),
                        "clothing": char.get("clothing", "unknown"),
                        "gender": char.get("gender", "unknown"),
                        "role": char.get("role", "unknown"),
                        "appears_in_chapters": [chapter_idx + 1],
                    }
                elif name:
                    all_chars[name]["appears_in_chapters"].append(chapter_idx + 1)

        return list(all_chars.values())

    def _split_paragraphs(self, text: str) -> List[str]:
        """Split chapter text into paragraphs."""
        # Split on double newlines or Chinese paragraph markers
        paragraphs = re.split(r"\n\s*\n", text)
        return [p.strip() for p in paragraphs if p.strip()]

    def _plan_single_shot(
        self, global_index: int, chapter_index: int, paragraph: str
    ) -> ShotDirective:
        """Plan a single shot from a paragraph.

        Args:
            global_index: Global shot index across all chapters.
            chapter_index: 1-based chapter index.
            paragraph: The paragraph text.

        Returns:
            A ShotDirective with all inferred metadata.
        """
        # Camera type: infer from content length and keywords
        shot_type = self._infer_shot_type(paragraph)

        # Characters present
        characters_present = self._find_characters_in_text(paragraph)

        # Dialogue extraction
        dialogue = self._extract_dialogue(paragraph)

        # Scene
        scene_name = self._match_scene(paragraph)

        # Action & emotion
        action = self._extract_action(paragraph)
        emotion = self._infer_emotion_from_text(paragraph)

        # Camera instruction
        camera = self._build_camera_instruction(shot_type, paragraph)

        # Raw prompt hint
        raw_prompt_hint = self._build_prompt_hint(
            characters_present, scene_name, shot_type, paragraph
        )

        return ShotDirective(
            index=global_index,
            chapter_index=chapter_index,
            shot_type=shot_type,
            camera=camera,
            characters_present=characters_present,
            scene_name=scene_name,
            dialogue=dialogue,
            narration=paragraph[:200],
            action=action,
            emotion=emotion,
            raw_prompt_hint=raw_prompt_hint,
        )

    def _infer_shot_type(self, paragraph: str) -> ShotType:
        """Infer the shot type from paragraph content.

        Rules:
            - Dialogue-heavy → CloseUp
            - Action / movement → Tracking or Wide
            - Description of scenery → Wide or Drone
            - Internal monologue → CloseUp
            - Default → Medium
        """
        dialogue_count = len(self.DIALOGUE_PATTERN.findall(paragraph))
        para_len = len(paragraph)

        # High dialogue density → CloseUp
        if dialogue_count >= 3:
            return ShotType.close_up

        # Description heavy → Wide
        descriptive_keywords = ["天空", "大地", "远方", "俯瞰", "全景", "风景"]
        if any(kw in paragraph for kw in descriptive_keywords):
            return ShotType.wide

        # Action words → Tracking
        action_keywords = ["跑", "追", "飞", "跳", "冲", "奔", "移动", "走"]
        if sum(paragraph.count(kw) for kw in action_keywords) >= 2:
            return ShotType.tracking

        # Very short dialogue → CloseUp
        if 0 < dialogue_count <= 2 and para_len < 200:
            return ShotType.close_up

        # Long descriptive → Wide
        if para_len > 500 and dialogue_count == 0:
            return ShotType.wide

        return ShotType.medium

    def _find_characters_in_text(self, text: str) -> List[str]:
        """Find which characters appear in this text.

        Matches full names, aliases, and given-name references
        (e.g., "栩栩" matches 关栩栩, "蕊蕊" matches 关蕊蕊).
        """
        present: List[str] = []
        for char in self.characters:
            if char.name in text:
                present.append(char.name)
                continue
            # Check aliases
            for alias in char.aliases:
                if alias in text and len(alias) >= 2:
                    present.append(char.name)
                    break
        return present

    def _extract_dialogue(self, text: str) -> str:
        """Extract dialogue lines from text, filtering onomatopoeia."""
        matches = self.DIALOGUE_PATTERN.findall(text)
        # Filter out onomatopoeia (single char like 哐/砰) and very short sounds
        dialogue_lines = [
            m for m in matches
            if len(m.strip()) >= 2 and not re.match(r'^[噼啪轰砰哐咚咔嗒嗖唰呼哈嘿嗯啊哦哎哟]$', m.strip())
        ]
        return "\n".join(dialogue_lines) if dialogue_lines else ""

    def _match_scene(self, text: str) -> str:
        """Match text to an identified scene."""
        for scene in self.scenes:
            if scene.location in text:
                return scene.name
        return ""

    def _extract_action(self, text: str) -> str:
        """Extract action descriptions from text."""
        action_keywords = [
            "跑", "追", "飞", "跳", "冲", "奔", "走", "站", "坐",
            "转身", "回头", "抬头", "低头", "挥手", "拔剑", "握拳",
            "奔跑", "跳跃", "飞行", "坠落", "攀爬",
        ]
        found = [kw for kw in action_keywords if kw in text]
        return "、".join(found) if found else "静止"

    def _infer_emotion_from_text(self, text: str) -> str:
        """Infer emotional state from text."""
        emotion_map = {
            "笑": "happy", "哭": "sad", "怒": "angry", "惊": "surprised",
            "怕": "fearful", "悲": "sorrowful", "喜": "joyful",
            "忧": "worried", "恨": "hateful", "爱": "loving",
            "叹息": "sighing", "沉默": "silent", "颤抖": "trembling",
        }
        for keyword, emotion in emotion_map.items():
            if keyword in text:
                return emotion
        return "neutral"

    def _build_camera_instruction(self, shot_type: ShotType, text: str) -> str:
        """Build a camera instruction string."""
        instructions: Dict[ShotType, str] = {
            ShotType.close_up: "Close-up on face, shallow depth of field, bokeh background",
            ShotType.medium: "Medium shot, waist-up framing, standard lens",
            ShotType.wide: "Wide establishing shot, deep focus, environmental context",
            ShotType.drone: "Aerial drone shot, top-down or high angle",
            ShotType.pov: "First-person POV, handheld feel, slight camera shake",
            ShotType.tracking: "Tracking shot following subject, motion blur on background",
        }
        return instructions.get(shot_type, "Standard shot")

    def _build_prompt_hint(
        self,
        characters: List[str],
        scene: str,
        shot_type: ShotType,
        paragraph: str,
    ) -> str:
        """Build a raw prompt hint for the Prompt Engine."""
        parts: List[str] = []

        if characters:
            parts.append(f"Characters: {', '.join(characters)}")
        if scene:
            parts.append(f"Scene: {scene}")
        parts.append(f"Shot type: {shot_type.value}")
        parts.append(f"Content: {paragraph[:150]}")

        return " | ".join(parts)

    # ----------------------------------------------------------
    # Phase 5: Output
    # ----------------------------------------------------------

    def to_parse_result(self) -> DirectorParseResult:
        """Convert internal state to a structured DirectorParseResult.

        Returns:
            DirectorParseResult ready for downstream consumption.
        """
        chapters_data: List[Dict[str, Any]] = []
        for i, chapter_text in enumerate(self.chapters):
            chapter_shots = [s for s in self.shots if s.chapter_index == i + 1]
            chapters_data.append({
                "index": i + 1,
                "title": self._extract_chapter_title(chapter_text),
                "text_length": len(chapter_text),
                "shot_count": len(chapter_shots),
                "shots": [
                    {
                        "index": shot.index,
                        "shot_type": shot.shot_type.value,
                        "camera": shot.camera,
                        "characters": shot.characters_present,
                        "scene": shot.scene_name,
                        "dialogue": shot.dialogue,
                        "action": shot.action,
                        "emotion": shot.emotion,
                    }
                    for shot in chapter_shots
                ],
            })

        characters_data = [
            {
                "name": char.name,
                "aliases": char.aliases,
                "gender": char.gender,
                "estimated_age": char.estimated_age,
                "role": char.role,
                "traits": char.traits,
                "appearance_hints": char.appearance_hints,
            }
            for char in self.characters
        ]

        scenes_data = [
            {
                "name": scene.name,
                "location": scene.location,
                "time_of_day": scene.time_of_day,
                "weather": scene.weather,
                "mood": scene.mood,
                "description": scene.description,
            }
            for scene in self.scenes
        ]

        return DirectorParseResult(
            chapters=chapters_data,
            characters=characters_data,
            scenes=scenes_data,
            total_shots=len(self.shots),
        )

    def _extract_chapter_title(self, chapter_text: str) -> str:
        """Extract chapter title from the first line."""
        first_line = chapter_text.split("\n")[0].strip()
        return first_line[:80] if first_line else f"Chapter"

    def run_full_pipeline(self, novel_path: str) -> DirectorParseResult:
        """Execute the complete AI Director pipeline.

        Args:
            novel_path: Path to the novel file.

        Returns:
            DirectorParseResult with full analysis.
        """
        logger.info("=" * 60)
        logger.info("AI Director: Starting full pipeline")
        logger.info("=" * 60)

        self.load_novel(novel_path)
        self.segment_chapters()
        self.extract_characters()
        self.identify_scenes()
        self.plan_shots()

        result = self.to_parse_result()
        logger.info(f"AI Director: Pipeline complete — {result.total_shots} shots planned")
        return result

    def run_full_pipeline_v2(self, novel_path: str) -> Dict[str, Any]:
        """Execute V2 three-role dispatch pipeline.

        QwenDirector(Qwen3-235B) → DeepSeekPlanner(DeepSeek R1) → Shot JSON
                                    ↓ (fallback)
                             LocalDirector(Qwen3-32B)

        Key rule: only QwenDirector touches raw novel text.
        DeepSeekPlanner receives structured dict only.

        Args:
            novel_path: Path to the novel file.

        Returns:
            Dict with characters, scenes, story_plan, and shots.
        """
        logger.info("=" * 60)
        logger.info("AI Director V2: Three-Role Dispatch pipeline")
        logger.info("=" * 60)

        self.load_novel(novel_path)
        self.segment_chapters()

        chapter_analysis: Dict[str, Any] = {}
        story_plan: List[Dict[str, Any]] = []

        # Stage 1: QwenDirector — story understanding
        if self._use_three_role and self._qwen_director:
            chapter_analysis = self._qwen_director.analyze_novel(self.novel_text)
            if chapter_analysis:
                logger.info(f"V2 QwenDirector: {len(chapter_analysis.get('chapters', []))} chapters analyzed")

                # Hydrate key_characters → CharacterProfile
                llm_chars = chapter_analysis.get("key_characters", [])
                if llm_chars:
                    self.characters = []
                    for c in llm_chars:
                        self.characters.append(CharacterProfile(
                            name=c.get("name", "Unknown"),
                            role=c.get("role", "supporting"),
                            traits=[c.get("desc", "")],
                        ))
                    logger.info(f"V2 QwenDirector: {len(self.characters)} characters identified")

                # Hydrate key_scenes → SceneInfo
                llm_scenes = chapter_analysis.get("key_scenes", [])
                if llm_scenes:
                    self.scenes = []
                    for s in llm_scenes:
                        self.scenes.append(SceneInfo(
                            name=s.get("location", "Unknown"),
                            location=s.get("location", ""),
                            mood=s.get("atmosphere", "neutral"),
                            description=s.get("description", ""),
                        ))
                    logger.info(f"V2 QwenDirector: {len(self.scenes)} scenes identified")

        if not chapter_analysis:
            # QwenDirector failed — fallback to legacy character/scene extraction
            logger.warning("V2 QwenDirector failed, falling back to rule-based extraction")
            self.extract_characters()
            self.identify_scenes()

        # Stage 2: DeepSeekPlanner — shot planning from structured analysis
        if self._use_three_role and self._deepseek_planner and chapter_analysis:
            llm_shots = self._deepseek_planner.plan_shots(chapter_analysis)
            if llm_shots:
                # Convert LLM shot dicts → ShotDirective list
                self.shots = []
                for s in llm_shots:
                    self.shots.append(ShotDirective(
                        index=s.get("index", 0),
                        chapter_index=s.get("chapter", 1),
                        shot_type=ShotType(s.get("shot_type", "medium")),
                        camera=s.get("camera", ""),
                        characters_present=s.get("characters", []),
                        scene_name=s.get("scene", ""),
                        dialogue=s.get("dialogue", ""),
                        action=s.get("action", ""),
                        emotion=s.get("emotion", ""),
                        narration=s.get("narration", ""),
                    ))
                logger.info(f"V2 DeepSeekPlanner: {len(self.shots)} shots planned")

        # Stage 3: LocalDirector fallback if both Qwen+DeepSeek failed
        if not self.shots and self._use_three_role and self._local_director:
            logger.warning("V2 DeepSeekPlanner failed, falling back to LocalDirector (Qwen3-32B)")
            local_result = self._local_director.run(self.novel_text)
            if local_result:
                llm_shots = local_result.get("shots", [])
                for s in llm_shots:
                    self.shots.append(ShotDirective(
                        index=s.get("index", 0),
                        chapter_index=s.get("chapter", 1),
                        shot_type=ShotType(s.get("shot_type", "medium")),
                        camera=s.get("camera", ""),
                        characters_present=s.get("characters", []),
                        scene_name=s.get("scene", ""),
                        dialogue=s.get("dialogue", ""),
                        action=s.get("action", ""),
                        emotion=s.get("emotion", ""),
                        narration=s.get("narration", ""),
                    ))
                logger.info(f"V2 LocalDirector: {len(self.shots)} shots planned")

        # Stage 4: Ultimate fallback — rule-based shot planning
        if not self.shots:
            logger.warning("V2 all LLM paths failed, using rule-based plan_shots")
            self.plan_shots()

        result = self.to_parse_result()
        logger.info(f"AI Director V2: Complete — {result.total_shots} shots")

        return {
            "parse_result": result,
            "story_plan": story_plan,
            "chapter_analysis": chapter_analysis,
            "characters": [
                {"name": c.name, "traits": c.traits, "appearance": c.appearance_hints}
                for c in self.characters
            ],
            "scenes": [
                {"name": s.name, "mood": s.mood, "weather": s.weather}
                for s in self.scenes
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        """Export the parse result as a JSON string."""
        result = self.to_parse_result()
        return json.dumps(result.model_dump(), ensure_ascii=False, indent=indent)


# ============================================================
# V2.0 — Hierarchical Data Structures
# ============================================================

@dataclass
class Beat:
    """节拍 — 最小的叙事单元.

    A beat is the smallest atomic unit of storytelling. Each beat
    represents a distinct emotional/action moment. A Scene contains
    multiple Beats, and each Beat may expand into 1-N Shots.
    """
    beat_id: str = ""
    beat_type: str = ""       # dialogue/action/monologue/transition/narration
    description: str = ""
    characters: List[str] = field(default_factory=list)
    emotion: str = "neutral"
    emotion_intensity: float = 0.5  # 0~1
    duration: float = 3.0    # seconds


@dataclass
class Shot:
    """镜头 — a Beat may expand into 1-N Shots.

    Each Shot has a unique camera setup, angle, and composition.
    Multiple Shots per Beat allow for shot-reverse-shot patterns,
    close-up + wide, or dynamic camera movement.
    """
    shot_id: str = ""
    chapter: int = 0
    scene: int = 0
    shot: int = 0
    camera: str = "medium"    # close-up/medium/full/over-shoulder/aerial/dutch/tracking/pov
    camera_angle: str = ""    # low angle, dutch tilt, etc.
    camera_motion: str = ""   # slow push-in, dolly left, etc.
    angle: str = "eye_level"  # eye_level/low/high/dutch/bird_eye/worm_eye
    duration: float = 3.0     # seconds
    action: str = ""
    composition: str = ""     # rule-of-thirds/golden-ratio/symmetrical/leading-lines/dynamic-diagonal
    focal_length: str = ""    # 24mm/35mm/50mm/85mm/135mm
    emotion: str = "neutral"
    atmosphere: str = ""
    dialogue: str = ""
    narration: str = ""
    characters: list = field(default_factory=list)
    background: str = ""
    background_image_path: str = ""  # filled by SceneStage
    weather: str = "clear"
    time_of_day: str = "noon"
    lighting: str = "natural"
    light_source: str = ""
    motion_hint: str = ""          # V3: preset motion from beat type (static/dynamic/subtle)
    color_palette: str = ""
    negative_prompt: str = ""
    voice: str = ""
    # generation params
    seed: int = -1
    steps: int = 30
    cfg: float = 7.0
    width: int = 3840
    height: int = 2160
    # pipeline tracking (filled at runtime)
    status: str = "waiting"
    image_path: str = ""
    video_path: str = ""
    json_path: str = ""
    thumbnail_path: str = ""
    error_message: str = ""
    retry_count: int = 0
    retry_max: int = 3
    image_model: str = ""
    video_model: str = ""
    control_workflow: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)  # V3.5 extension data (prompts, upscale metadata, etc.)


@dataclass
class Scene:
    """场景 — contains Beats and expanded Shots.

    A Scene is defined by a single location/time/weather combination.
    The AI Director identifies scene boundaries based on location changes
    or significant time jumps.
    """
    scene_id: str = ""
    chapter_idx: int = 0
    location: str = ""
    time: str = "day"         # dawn/morning/noon/afternoon/dusk/night
    weather: str = "clear"
    emotion: str = "neutral"
    mood: str = "neutral"     # majestic/mysterious/tense/peaceful/melancholic/surreal/oppressive
    beats: List[Beat] = field(default_factory=list)
    shots: List[Shot] = field(default_factory=list)  # expanded from all Beats


@dataclass
class Chapter:
    """章节 — the top-level structural unit.

    One Chapter contains multiple Scenes. The Chapter carries
    a summary and the ordered list of its Scenes. This is the
    primary output of the hierarchical parsing pipeline.
    """
    chapter_id: str = ""
    title: str = ""
    scenes: List[Scene] = field(default_factory=list)
    summary: str = ""
    chapter_idx: int = 0


# ============================================================
# V2.0 — Hierarchical Parsing
# ============================================================

class HierarchicalDirector:
    """V2.0 hierarchical novel parsing engine.

    Replaces flat shot planning with a deep narrative structure:
      Novel → Chapters → Scenes → Beats → Shots

    This enables:
      - StoryGraph semantic graph construction
      - Beat-level emotion curve tracking
      - Scene-context-aware prompt generation
      - Dynamic camera assignment per Beat expansion

    Usage:
        director = HierarchicalDirector()
        chapters = director.parse_hierarchical(novel_text)
        # → List[Chapter] ready for StoryGraphParser
    """

    # Shot expansion templates per beat type
    BEAT_SHOT_EXPANSION: Dict[str, List[dict]] = {
        "dialogue": [
            {"camera": "medium", "angle": "eye_level", "composition": "rule-of-thirds"},
            {"camera": "close-up", "angle": "eye_level", "composition": "centered"},
        ],
        "action": [
            {"camera": "wide", "angle": "eye_level", "composition": "dynamic-diagonal"},
            {"camera": "medium", "angle": "low", "composition": "leading-lines"},
        ],
        "monologue": [
            {"camera": "close-up", "angle": "eye_level", "composition": "centered"},
            {"camera": "medium", "angle": "dutch", "composition": "golden-ratio"},
        ],
        "transition": [
            {"camera": "wide", "angle": "bird_eye", "composition": "symmetrical"},
        ],
        "narration": [
            {"camera": "wide", "angle": "eye_level", "composition": "golden-ratio"},
            {"camera": "medium", "angle": "low", "composition": "leading-lines"},
        ],
    }

    def parse_hierarchical(self, novel_text: str) -> List[Chapter]:
        """Parse novel text into hierarchical Chapter→Scene→Beat→Shot structure.

        Algorithm (rule-based, no LLM dependency):
          1. Split text into chapters by heading markers
          2. Within each chapter, detect scene boundaries (location/time changes)
          3. Within each scene, split text into beats (paragraphs/sentences)
          4. Classify each beat by type (dialogue/action/monologue/etc.)
          5. Expand each beat into 1-3 shots with auto-assigned camera/angle

        Args:
            novel_text: Full novel text as a single string.

        Returns:
            List of Chapter objects, each containing Scenes→Beats→Shots.
        """
        logger.info("HierarchicalDirector: Starting hierarchical parse")

        # Step 1: Split into chapters
        raw_chapters = self._split_chapters(novel_text)
        logger.info(f"HierarchicalDirector: {len(raw_chapters)} raw chapters found")

        chapters: List[Chapter] = []

        for ch_idx, ch_text in enumerate(raw_chapters):
            chapter = self._parse_chapter(ch_text, ch_idx + 1)
            chapters.append(chapter)
            beat_count = sum(len(scene.beats) for scene in chapter.scenes)
            shot_count = sum(len(scene.shots) for scene in chapter.scenes)
            logger.info(
                f"HierarchicalDirector: ch{ch_idx+1:02d} '{chapter.title}' — "
                f"{len(chapter.scenes)} scenes, {beat_count} beats, {shot_count} shots"
            )

        total_beats = sum(
            len(scene.beats) for ch in chapters for scene in ch.scenes
        )
        total_shots = sum(
            len(scene.shots) for ch in chapters for scene in ch.scenes
        )
        logger.info(
            f"HierarchicalDirector: Complete — "
            f"{len(chapters)} chapters, {total_beats} beats, {total_shots} shots"
        )
        return chapters

    def _split_chapters(self, text: str) -> List[str]:
        """Split novel text into chapters using heuristics.

        Detects:
          - "第X章" patterns (Chinese)
          - "Chapter X" patterns (English)
          - "## Chapter" markdown headings
          - Double-newline-separated major breaks as fallback
        """
        import re

        # Try chapter markers first
        patterns = [
            r'(?:^|\n)(第[零一二三四五六七八九十百千\d]+章[^\n]*)',
            r'(?:^|\n)(第\d+章[^\n]*)',
            r'(?:^|\n)(Chapter\s+\d+[^\n]*)',
            r'(?:^|\n)(##\s*Chapter\s+\d+[^\n]*)',
        ]

        for pattern in patterns:
            splits = re.split(pattern, text, flags=re.MULTILINE)
            # Rejoin: pattern groups get their own segment
            if len(splits) > 1:
                chapters: List[str] = []
                current = ""
                for seg in splits:
                    seg = seg.strip()
                    if not seg:
                        continue
                    # Check if this segment looks like a chapter heading
                    if re.match(r'第[零一二三四五六七八九十百千\d]+章|Chapter\s+\d+|##\s*Chapter', seg):
                        if current:
                            chapters.append(current)
                        current = seg
                    else:
                        if current:
                            current += "\n\n" + seg
                        else:
                            current = seg
                if current:
                    chapters.append(current)
                if len(chapters) >= 2:
                    return chapters

        # Fallback: split on double newlines into chunks of ~2000 chars
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(paragraphs) <= 1:
            return [text]

        chapters = []
        current = ""
        for p in paragraphs:
            if len(current) + len(p) > 3000 and current:
                chapters.append(current)
                current = p
            else:
                current = (current + "\n\n" + p).strip()
        if current:
            chapters.append(current)

        return chapters if chapters else [text]

    def _parse_chapter(self, text: str, ch_idx: int) -> Chapter:
        """Parse a single chapter into Scenes, Beats, and Shots."""
        # Extract title from first line
        lines = text.strip().split("\n")
        title = lines[0].strip() if lines else f"Chapter {ch_idx}"

        # Step 2: Detect scene boundaries
        scene_texts = self._split_scenes(text)

        # Step 3-5: Parse each scene
        scenes: List[Scene] = []
        for sc_idx, sc_text in enumerate(scene_texts):
            scene = self._parse_scene(sc_text, ch_idx, sc_idx + 1)
            scenes.append(scene)

        return Chapter(
            chapter_id=f"ch{ch_idx:02d}",
            title=title,
            scenes=scenes,
            summary=self._extract_summary(text),
            chapter_idx=ch_idx,
        )

    def _split_scenes(self, chapter_text: str) -> List[str]:
        """Detect scene boundaries within a chapter.

        Scene boundaries are indicated by:
          - Location change markers (在.../...里/...前/...外)
          - Time change markers (第二天/几小时后/傍晚/深夜)
          - Explicit scene breaks (*** / --- / •••)
          - Significant paragraph breaks (3+ blank lines)
        """
        import re

        # Try explicit breaks first
        if re.search(r'\n\s*[*\\-•]{3,}\s*\n', chapter_text):
            return [s.strip() for s in re.split(r'\n\s*[*\\-•]{3,}\s*\n', chapter_text) if s.strip()]

        # Split by paragraphs
        paragraphs = [p.strip() for p in chapter_text.split("\n\n") if p.strip()]

        if len(paragraphs) <= 2:
            return [chapter_text] if chapter_text.strip() else []

        # Group small paragraphs with their context
        scenes: List[str] = []
        current = ""

        scene_markers = [
            r'在[^\s，。]{1,8}(里|内|中|前|外|旁|下|上)',
            r'(第二天|次日|几天后|数日后|不久后|转眼|傍晚|深夜|清晨|午后|黄昏|黎明)',
            r'(镜头|画面|场景)(一转|切换|转到|来到)',
        ]

        for p in paragraphs:
            is_boundary = any(re.search(m, p) for m in scene_markers)

            if is_boundary and current:
                scenes.append(current)
                current = p
            else:
                if current:
                    current += "\n\n" + p
                else:
                    current = p

        if current:
            scenes.append(current)

        return scenes if scenes else [chapter_text]

    def _parse_scene(self, text: str, ch_idx: int, sc_idx: int) -> Scene:
        """Parse a scene into Beats and expanded Shots."""
        import re

        # Extract location, time, weather, emotion from scene text
        location = ""
        time_of_day = "day"
        weather = "clear"
        emotion = "neutral"
        mood = "neutral"

        # Location extraction
        loc_match = re.search(r'在([^\s，。]{1,10})(里|内|中|前|外|旁|下|上)', text)
        if loc_match:
            location = loc_match.group(1)

        # Time extraction
        time_map = {
            "清晨": "dawn", "早晨": "morning", "早上": "morning", "上午": "morning",
            "中午": "noon", "下午": "afternoon", "午后": "afternoon",
            "傍晚": "dusk", "黄昏": "dusk",
            "夜晚": "night", "晚上": "night", "深夜": "night", "半夜": "night",
        }
        for cn, en in time_map.items():
            if cn in text:
                time_of_day = en
                break

        # Weather
        weather_map = {
            "雨": "rain", "下雨": "rain", "暴雨": "heavy_rain",
            "雪": "snow", "下雪": "snow", "暴雪": "heavy_snow",
            "阴": "overcast", "雾": "fog", "风": "windy",
            "晴": "clear", "阳光": "clear",
        }
        for cn, en in weather_map.items():
            if cn in text[:200]:
                weather = en
                break

        # Emotion
        emotion_map = {
            "怒": "angry", "愤怒": "angry", "生气": "angry",
            "悲": "sad", "悲伤": "sad", "伤心": "sad", "哭": "sad",
            "喜": "happy", "高兴": "happy", "笑": "happy", "开心": "happy",
            "怕": "fearful", "恐惧": "fearful", "害怕": "fearful",
            "惊": "surprised", "惊讶": "surprised",
        }
        for cn, en in emotion_map.items():
            if cn in text[:300]:
                emotion = en
                break

        # Derive lighting from time_of_day (V3 cinema upgrade)
        lighting = self._LIGHTING_MAP.get(time_of_day, "natural lighting")

        # Split into beats (sentences or short paragraphs)
        beat_texts = self._split_beats(text)

        # Parse each beat
        beats: List[Beat] = []
        shots: List[Shot] = []
        shot_counter = 0

        for bt_idx, bt_text in enumerate(beat_texts):
            beat = self._parse_beat(bt_text, ch_idx, sc_idx, bt_idx + 1)
            beats.append(beat)

            # Expand beat into shots (V3: with scene lighting)
            expanded = self._expand_beat_to_shots(
                beat, ch_idx, sc_idx, shot_counter, lighting=lighting,
            )
            shots.extend(expanded)
            shot_counter += len(expanded)

        # V3 Cinema Rhythm: enforce shot type pattern per scene
        #  Rule: first shot → wide (establishing), last shot → medium/wide (closing),
        #        middle shots → alternate medium/close-up
        if len(shots) >= 3:
            # Force first shot to wide
            shots[0].camera = "wide"
            shots[0].focal_length = "24mm"
            # Force last shot to medium or wide
            shots[-1].camera = "wide" if len(shots) % 2 == 0 else "medium"
            shots[-1].focal_length = "24mm" if shots[-1].camera == "wide" else "50mm"
            # Middle shots: alternate medium / close-up
            for i in range(1, len(shots) - 1):
                shots[i].camera = "medium" if i % 2 == 1 else "close-up"
                shots[i].focal_length = "50mm" if shots[i].camera == "medium" else "85mm"
        elif len(shots) == 2:
            shots[0].camera = "wide"
            shots[0].focal_length = "24mm"
            shots[-1].camera = "medium"
            shots[-1].focal_length = "50mm"
        elif len(shots) == 1:
            shots[0].camera = "medium"
            shots[0].focal_length = "50mm"

        return Scene(
            scene_id=f"sc_{ch_idx:02d}_{sc_idx:02d}",
            chapter_idx=ch_idx,
            location=location,
            time=time_of_day,
            weather=weather,
            emotion=emotion,
            mood=mood,
            beats=beats,
            shots=shots,
        )

    def _split_beats(self, scene_text: str) -> List[str]:
        """Split scene text into beat-level units.

        Beats are typically:
          - Dialogue lines (「...」 or "...")
          - Action paragraphs
          - Descriptive narration
        """
        import re

        # Extract dialogue as separate beats
        dialogue_pattern = r'[「『""]([^」』""]+)[」』""]'

        # If text contains multiple dialogue lines, split around them
        parts = re.split(f'({dialogue_pattern})', scene_text)

        beats: List[str] = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Skip if it's a captured dialogue text (will be included in its context)
            if re.match(r'^[「『""].*[」』""]$', part):
                continue
            # Skip pure dialogue captures without quotes
            if len(part) < 50 and not re.search(r'[。！？.!?]', part):
                continue
            beats.append(part)

        # If no beats found, use paragraph split
        if not beats:
            beats = [p.strip() for p in scene_text.split("\n") if p.strip()]

        # If still no beats, use sentence split
        if not beats:
            sentences = re.split(r'[。！？.!?]', scene_text)
            beats = [s.strip() for s in sentences if len(s.strip()) > 10]

        return beats if beats else [scene_text]

    def _parse_beat(
        self, text: str, ch_idx: int, sc_idx: int, bt_idx: int
    ) -> Beat:
        """Classify and parse a single beat."""
        import re

        # Detect beat type
        has_dialogue = bool(re.search(r'[「『""]([^」』""]+)[」』""]', text))
        has_action_verbs = bool(re.search(
            r'(走|跑|跳|打|拿|放|推|拉|坐|站|躺|飞|冲|抱|摔|踢|拍|挥|指|转身|回头|起身|抬头|低头)',
            text,
        ))
        has_monologue = bool(re.search(r'(心想|暗想|心道|思忖|暗道|默念)', text))

        if has_dialogue:
            beat_type = "dialogue"
        elif has_monologue:
            beat_type = "monologue"
        elif has_action_verbs:
            beat_type = "action"
        elif len(text) < 30:
            beat_type = "transition"
        else:
            beat_type = "narration"

        # Extract characters
        characters = self._extract_char_names(text)

        # Extract emotion
        emotion = "neutral"
        emotion_map = {
            "怒": "angry", "愤怒": "angry", "悲": "sad", "悲伤": "sad",
            "喜": "happy", "高兴": "happy", "怕": "fearful", "恐惧": "fearful",
            "惊": "surprised", "惊讶": "surprised",
        }
        for cn, en in emotion_map.items():
            if cn in text[:100]:
                emotion = en
                break

        # Duration estimation
        duration = self._estimate_duration(text, beat_type)

        return Beat(
            beat_id=f"bt_{ch_idx:02d}_{sc_idx:02d}_{bt_idx:03d}",
            beat_type=beat_type,
            description=text[:200],
            characters=characters,
            emotion=emotion,
            emotion_intensity=0.5,
            duration=duration,
        )

    # Lighting lookup: time_of_day → lighting description
    _LIGHTING_MAP: Dict[str, str] = {
        "dawn": "soft morning light, golden hour glow, warm tones",
        "morning": "bright morning light, clear sky, crisp shadows",
        "noon": "harsh overhead light, strong shadows, high contrast",
        "afternoon": "warm afternoon light, soft shadows, golden tint",
        "dusk": "golden hour, warm orange glow, long shadows, cinematic rim light",
        "night": "warm night lighting, soft ambient glow, practical lights, dim atmosphere",
    }

    # Motion hint per beat type
    _MOTION_HINT_MAP: Dict[str, str] = {
        "dialogue": "static, subtle gestures, lip sync",
        "action": "dynamic, fast movement, directional motion blur",
        "monologue": "subtle, slow micro-expressions, stillness",
        "transition": "static, environmental focus",
        "narration": "slow pan, ambient motion",
    }

    def _expand_beat_to_shots(
        self,
        beat: Beat,
        ch_idx: int,
        sc_idx: int,
        shot_offset: int,
        lighting: str = "",
    ) -> List[Shot]:
        """Expand a Beat into 1-3 Shots based on beat type templates (V3 cinema upgrade).

        Each beat type has a default camera pattern. The expansion
        auto-assigns camera type, angle, composition, lighting, emotion
        and motion_hint. Per V3 cinema pipeline, no LLM involved — pure
        template assembly.

        Args:
            beat: The Beat to expand.
            ch_idx: Chapter index.
            sc_idx: Scene index.
            shot_offset: Starting shot number offset.
            lighting: Inherited scene lighting description (derived from time_of_day).
        """
        templates = self.BEAT_SHOT_EXPANSION.get(beat.beat_type, [
            {"camera": "medium", "angle": "eye_level", "composition": "rule-of-thirds"},
        ])

        shots: List[Shot] = []
        shot_duration = beat.duration / len(templates)

        # Motion hint from beat type
        motion_hint = self._MOTION_HINT_MAP.get(beat.beat_type, "static")

        for i, tmpl in enumerate(templates):
            shot_id = f"sh_{ch_idx:02d}_{sc_idx:02d}_{shot_offset + i + 1:03d}"
            camera = tmpl.get("camera", "medium")

            # Focal length inference
            focal_map = {"close-up": "85mm", "medium": "50mm", "wide": "24mm"}
            focal_length = focal_map.get(camera, "50mm")

            shots.append(Shot(
                shot_id=shot_id,
                chapter=ch_idx,
                scene=sc_idx,
                shot=shot_offset + i + 1,
                camera=camera,
                angle=tmpl.get("angle", "eye_level"),
                duration=round(shot_duration, 1),
                action=beat.description[:100],
                composition=tmpl.get("composition", "rule-of-thirds"),
                focal_length=focal_length,
                # V3 cinema fields
                emotion=beat.emotion,           # inherited from Beat
                lighting=lighting,              # inherited from SceneDNA
                motion_hint=motion_hint,        # derived from beat_type
            ))

        return shots

    def _extract_char_names(self, text: str) -> List[str]:
        """Extract character names from text using heuristics.

        Detects Chinese names (2-3 characters), filtered against:
          - NON_NAME_WORDS (common false positives)
          - SURNAME_NAME_PATTERN (must start with known surname)
          - NON_PERSON_SUFFIXES (family/company terms)
        """
        import re

        # Inline surname list — avoids dependency on AIDirector class constants
        _SURNAMES = (
            "王李张刘陈杨黄赵周吴徐孙马胡朱郭何罗高林梁郑谢宋唐许邓冯韩曹曾彭萧"
            "潘田董袁于叶蒋杜苏魏薛丁沈范江傅钟卢汪戴崔任陆廖姚方金邱夏谭韦贾邹"
            "石熊孟秦阎侯白龙段雷钱汤尹易常武乔贺赖龚文关褚姜古姚"
        )
        _NON_NAME = {
            "可以", "已经", "没有", "自己", "他们", "我们", "这个", "那个", "什么",
            "不过", "不是", "还是", "只是", "但是", "因为", "所以", "如果", "虽然",
            "一定", "一下", "一起", "一样", "一点", "也是", "就是", "还有", "不会",
            "出来", "起来", "看到", "知道", "觉得", "说道", "问道", "听到", "想到",
            "到了", "这里", "那里", "她的", "他的", "你的", "我的", "看着", "想着",
            "说着", "拿着", "以为", "发现", "忽然", "突然", "并未", "似乎", "已经",
            "出了", "开了", "入了", "进了", "走了", "上了", "也能", "也要", "也会",
            "还能", "还要", "又是", "还没", "整个", "两个", "三个", "几个", "一片",
            "一切", "一边", "一面", "居然", "当然", "果然", "竟然", "自然", "不再",
            "不如", "不能", "如何", "何必", "何况", "这可", "那是", "真是", "总是",
            "确实", "肯定", "完全", "简直", "几乎", "刚才", "曾经", "怎么办",
            "什么事", "一个人", "怎么回事", "没想到", "忍不住", "笑了笑", "下意识",
            "姜家人", "关家人", "姜海集", "姜家", "关家的", "关家",
            "张口却", "金光", "行李箱", "关父和", "姜姓", "有关", "关乎",
        }
        _NON_SUFFIXES = ("家", "家人", "家的", "氏", "姓", "集团", "集")
        _SURNAME_PAT = re.compile(rf'([{_SURNAMES}][\u4e00-\u9fff]{{1,2}})')

        names: set = set()
        speech_verbs = r'(?:说|道|问|答|喊|叫|笑|哭|怒|喝|叹|喃喃|低语|轻声道|开口道|问道|说道|回答)'

        # Strategy 1: Surname + speech verb
        for m in re.finditer(rf'({_SURNAME_PAT.pattern}){speech_verbs}', text):
            name = m.group(1)
            if (len(name) >= 2 and name not in _NON_NAME
                    and not name.endswith(_NON_SUFFIXES)):
                names.add(name)

        # Strategy 2: Prose dialogue attribution patterns
        _PROSE_PATTERNS = [
            re.compile(r'["\u201d](?:[，,])?\s*([\u4e00-\u9fff]{2,4})'
                       r'(?:柔声|冷声|低声|小声|大声|轻声|怒声|沉声)?'
                       r'(?:说|道|问|开口|冷哼|喊道|骂道|安慰|打断|附和|提醒)'),
            re.compile(r'([\u4e00-\u9fff]{2,4})'
                       r'(?:柔声|冷声|低声|小声|大声)?'
                       r'(?:说|道|问|开口|冷哼|喊道|骂道|安慰|打断|提问|开口问道|说道)'
                       r'[：:,，]?\s*["\u201c]'),
            re.compile(r'([\u4e00-\u9fff]{2,4})'
                       r'(?:看|见|听|走|站|坐|拿|放|转身|回头|抬头|低头|上前|拉住|接过|推开|挡在|冷笑|皱眉|摇头|点头|站起身)'
                       r'[^，。]{0,20}["\u201c]'),
        ]
        for pattern in _PROSE_PATTERNS:
            for name in pattern.findall(text):
                if (len(name) >= 2 and name not in _NON_NAME
                        and _SURNAME_PAT.match(name)):
                    names.add(name)

        # Strategy 3: Fallback — any 2-3 char before speech verb, with blacklist
        if len(names) < 2:
            for m in re.finditer(rf'([\u4e00-\u9fff]{{2,3}}){speech_verbs}', text):
                name = m.group(1)
                if (len(name) >= 2 and name not in _NON_NAME
                        and not name.endswith(_NON_SUFFIXES)):
                    names.add(name)

        return sorted(names)[:6]  # max 6 characters per beat

    def _estimate_duration(self, text: str, beat_type: str) -> float:
        """Estimate beat duration from text length and type.

        ~3 chars/sec for Chinese reading speed.
        """
        char_count = len(text)
        base_duration = char_count / 3.0  # ~3 chars/sec

        # Type modifiers
        modifiers = {
            "dialogue": 1.0,
            "action": 0.7,
            "monologue": 1.3,
            "transition": 0.4,
            "narration": 1.1,
        }
        mod = modifiers.get(beat_type, 1.0)
        duration = base_duration * mod

        # Clamp to reasonable range
        return max(1.5, min(duration, 15.0))

    def _extract_summary(self, text: str) -> str:
        """Extract a brief summary from chapter text."""
        # Simple: first non-title sentence up to 100 chars
        lines = text.strip().split("\n")
        for line in lines[1:]:  # skip title
            line = line.strip()
            if len(line) > 20:
                return line[:150]
        return text[:100].replace("\n", " ")

    def dump_hierarchy(self, chapters: List[Chapter]) -> str:
        """Debug: print the full chapter→scene→beat→shot hierarchy."""
        lines = []
        for ch in chapters:
            lines.append(f"\n{'='*60}")
            lines.append(f"Chapter {ch.chapter_idx}: {ch.title}")
            lines.append(f"Summary: {ch.summary[:100]}")
            for sc in ch.scenes:
                lines.append(f"  Scene {sc.scene_id}: {sc.location} | {sc.time} | {sc.weather} | {sc.emotion}")
                for bt in sc.beats:
                    lines.append(f"    Beat {bt.beat_id}: [{bt.beat_type}] {bt.description[:80]}...")
                for sh in sc.shots:
                    lines.append(f"      Shot {sh.shot_id}: [{sh.camera}/{sh.angle}] {sh.composition}")
        return "\n".join(lines)

    # ============================================================
    # V3.5 Engine Integration
    # ============================================================

    def init_v35_engines(self) -> bool:
        """Lazy-load all V3.5 AI engines.

        Returns:
            True if all engines were loaded successfully.
        """
        if self._v35_enabled:
            return True

        try:
            from backend.storyboard_engine import StoryboardEngine
            from backend.camera_planner import CameraPlanner
            from backend.motion_planner import MotionPlanner
            from backend.character_reasoner import CharacterReasoner
            from backend.scene_reasoner import SceneReasoner
            from backend.image_prompt_builder import ImagePromptBuilder
            from backend.video_prompt_builder import VideoPromptBuilder
            from backend.dialogue_optimizer import DialogueOptimizer

            self._v35_storyboard = StoryboardEngine()
            self._v35_camera = CameraPlanner()
            self._v35_motion = MotionPlanner()
            self._v35_char_reasoner = CharacterReasoner()
            self._v35_scene_reasoner = SceneReasoner()
            self._v35_img_builder = ImagePromptBuilder()
            self._v35_video_builder = VideoPromptBuilder()
            self._v35_dialogue_opt = DialogueOptimizer()
            self._v35_enabled = True
            logger.info("AI Director: V3.5 engines initialized (8 engines loaded)")
            return True
        except ImportError as e:
            logger.warning(f"AI Director: V3.5 engine import failed: {e}")
            self._v35_enabled = False
            return False
        except Exception as e:
            logger.warning(f"AI Director: V3.5 engine init failed: {e}")
            self._v35_enabled = False
            return False

    def upgrade_shots_v35(self) -> List[Dict[str, Any]]:
        """Enrich planned shots with V3.5 engines.

        Post-processes self.shots through:
          1. CharacterReasoner → enhanced character DNA
          2. SceneReasoner → enriched scene DNA
          3. CameraPlanner → camera config per shot
          4. MotionPlanner → motion description per shot
          5. ImagePromptBuilder → structured Flux prompt per shot
          6. VideoPromptBuilder → structured Wan prompt per shot
          7. DialogueOptimizer → emotion vectors per dialogue line

        Returns:
            List of enriched shot dicts with V3.5 PromptV35 fields.
        """
        if not self._v35_enabled:
            if not self.init_v35_engines():
                logger.warning("AI Director: V3.5 engines unavailable, skipping upgrade")
                return []

        logger.info(f"AI Director: V3.5 upgrading {len(self.shots)} shots ...")

        # Extract character list from existing profiles
        character_list = [c.name for c in self.characters] if self.characters else []
        character_dna_list = []
        for char in self.characters:
            try:
                char_dna = self._v35_char_reasoner.reason(
                    getattr(char, 'description', char.name),
                    None,
                )
                character_dna_list.append(char_dna)
            except Exception as e:
                logger.debug(f"CharacterReasoner failed for {char.name}: {e}")

        # Extract scene list
        scene_list = [s.name for s in self.scenes] if self.scenes else []

        enriched_shots = []
        for shot in self.shots:
            shot_dict = {
                "index": shot.index,
                "chapter_index": getattr(shot, "chapter_index", 0),
                "shot_type": shot.shot_type.value if hasattr(shot.shot_type, "value") else str(shot.shot_type),
                "camera": shot.camera,
                "characters_present": shot.characters_present,
                "scene_name": shot.scene_name,
                "dialogue": shot.dialogue,
                "narration": shot.narration,
                "action": shot.action,
                "emotion": shot.emotion,
            }

            # Camera planning
            try:
                emotion_intensity = self._estimate_emotion_intensity(shot.emotion)
                camera_config = self._v35_camera.plan_camera(
                    scene_description=shot.narration[:200] or shot.scene_name,
                    emotion_intensity=emotion_intensity,
                    character_count=len(shot.characters_present) if shot.characters_present else 1,
                )
                shot_dict["camera_config"] = camera_config
            except Exception as e:
                logger.debug(f"CameraPlanner failed for shot {shot.index}: {e}")
                shot_dict["camera_config"] = {}

            # Motion planning
            try:
                motion_config = self._v35_motion.generate_motion(
                    character_info={"name": shot.characters_present[0] if shot.characters_present else "unknown"},
                    dialogue_context=shot.dialogue or "",
                    emotion_vector=[],  # Will be filled by DialogueOptimizer
                )
                shot_dict["motion_config"] = motion_config
            except Exception as e:
                logger.debug(f"MotionPlanner failed for shot {shot.index}: {e}")
                shot_dict["motion_config"] = {}

            # Image prompt building
            try:
                img_prompt = self._v35_img_builder.build(
                    shot_data={
                        "characters": shot.characters_present,
                        "scene": shot.scene_name,
                        "action": shot.action or "",
                    }
                )
                shot_dict["image_prompt"] = getattr(img_prompt, "full_prompt", str(img_prompt))
            except Exception as e:
                logger.debug(f"ImagePromptBuilder failed for shot {shot.index}: {e}")
                shot_dict["image_prompt"] = ""

            # Video prompt building
            try:
                video_prompt = self._v35_video_builder.build(
                    shot_data={
                        "characters": shot.characters_present,
                        "scene": shot.scene_name,
                        "action": shot.action or "",
                    },
                    motion_plan=shot_dict.get("motion_config", {}),
                    camera_plan=shot_dict.get("camera_config", {}),
                    dialogue=shot.dialogue or "",
                )
                shot_dict["video_prompt"] = getattr(video_prompt, "full_prompt", str(video_prompt))
            except Exception as e:
                logger.debug(f"VideoPromptBuilder failed for shot {shot.index}: {e}")
                shot_dict["video_prompt"] = ""

            enriched_shots.append(shot_dict)

        # Dialogue optimization (batch)
        if enriched_shots:
            try:
                dialogue_lines = [
                    sh.get("dialogue", "") or sh.get("narration", "")[:100]
                    for sh in enriched_shots
                ]
                optimized = self._v35_dialogue_opt.optimize(
                    script_lines=dialogue_lines,
                    character_list=character_list or ["旁白"],
                )
                for i, (line_no, role, emotion_vec, tts_params) in enumerate(optimized):
                    if i < len(enriched_shots):
                        enriched_shots[i]["dialogue_emotion"] = {
                            "line_no": line_no,
                            "role": role,
                            "emotion_vector": emotion_vec,
                            "tts_params": tts_params,
                        }
            except Exception as e:
                logger.debug(f"DialogueOptimizer failed: {e}")

        logger.info(
            f"AI Director: V3.5 upgrade complete — {len(enriched_shots)} shots enriched"
        )
        return enriched_shots

    @staticmethod
    def _estimate_emotion_intensity(emotion: str) -> float:
        """Estimate emotion intensity from emotion label."""
        intensity_map = {
            "angry": 0.9, "fearful": 0.8, "happy": 0.7, "surprised": 0.8,
            "sad": 0.6, "neutral": 0.3, "tense": 0.7, "excited": 0.8,
        }
        return intensity_map.get(str(emotion).lower(), 0.5)
