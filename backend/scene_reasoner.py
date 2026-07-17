"""
AI Manga Studio V3.5 — Scene Reasoner

Enhances Scene DNA with structured scene elements and six-grid decomposition.
Source: 最新6宫格.txt

Key rules:
- Break long scenes into 6 key frames based on rhythm breakpoints
- Extract scene_elements, atmosphere, time_of_day, weather, environment_tags
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Data Models ───────────────────────────────────────────────

@dataclass
class SceneFrame:
    """Single frame in the six-grid decomposition."""
    frame_id: int = 0                     # 1-6
    description: str = ""                 # Frame description
    key_action: str = ""                  # Key action in this frame
    composition_hint: str = ""            # Composition suggestion
    emotional_peak: float = 0.0           # Emotional intensity (0-1)


@dataclass
class SceneDNAEnhanced:
    """Enhanced Scene DNA with structured fields."""
    scene_name: str = ""

    # Scene elements
    scene_elements: List[str] = field(default_factory=list)   # Environment objects/items

    # Atmosphere
    atmosphere: str = ""                                       # 氛围：紧张/温馨/悲壮等

    # Time and weather
    time_of_day: str = ""                                      # 时间：清晨/正午/黄昏/夜晚
    weather: str = ""                                          # 天气：晴/雨/雪/雾

    # Environment tags
    environment_tags: List[str] = field(default_factory=list)  # Style/quality tags

    # Six-grid decomposition
    six_grid: List[SceneFrame] = field(default_factory=list)   # 6 key frames

    # Continuity
    previous_scene: str = ""
    next_scene: str = ""


# ── Engine ────────────────────────────────────────────────────

class SceneReasoner:
    """Enhances Scene DNA with structured decomposition.

    Uses the six-grid approach to break long scenes into
    6 key visual frames for consistent image generation.
    """

    GRID_FRAMES: int = 6

    def __init__(self) -> None:
        logger.info("SceneReasoner initialized (V3.5)")

    # ── Public API ────────────────────────────────────────

    def reason(
        self,
        novel_text: str,
        character_list: List[str],
    ) -> SceneDNAEnhanced:
        """Generate enhanced Scene DNA from novel text.

        Args:
            novel_text: The novel text segment describing the scene.
            character_list: List of character names present.

        Returns:
            Enhanced SceneDNA with scene elements and six-grid.
        """
        dna = SceneDNAEnhanced()

        # Extract scene meta
        dna.atmosphere = self._extract_atmosphere(novel_text)
        dna.time_of_day = self._extract_time_of_day(novel_text)
        dna.weather = self._extract_weather(novel_text)
        dna.scene_elements = self._extract_scene_elements(novel_text)

        # Generate six-grid decomposition
        dna.six_grid = self._generate_six_grid(novel_text, character_list)

        # Generate environment tags
        dna.environment_tags = self._generate_tags(dna)

        logger.info(
            f"SceneReasoner: reasoned scene with {len(dna.scene_elements)} elements, "
            f"atmosphere='{dna.atmosphere}'"
        )
        return dna

    def reason_batch(
        self,
        scenes: List[Dict[str, Any]],
        character_list: List[str],
    ) -> List[SceneDNAEnhanced]:
        """Process multiple scenes in batch.

        Args:
            scenes: List of scene dicts with at minimum 'text' key.
            character_list: Shared character list.

        Returns:
            List of SceneDNAEnhanced, one per scene.
        """
        results: List[SceneDNAEnhanced] = []

        for scene in scenes:
            dna = self.reason(
                novel_text=scene.get("text", ""),
                character_list=character_list,
            )
            dna.scene_name = scene.get("name", "")
            dna.previous_scene = scene.get("previous", "")
            dna.next_scene = scene.get("next", "")
            results.append(dna)

        return results

    # ── Internal extraction methods ───────────────────────

    def _extract_atmosphere(self, text: str) -> str:
        """Heuristic atmosphere extraction from text."""
        atmosphere_keywords = {
            "紧张": ["紧张", "对峙", "逼迫", "急促"],
            "温馨": ["温暖", "温馨", "柔和", "微笑", "幸福"],
            "悲壮": ["悲壮", "牺牲", "倒下", "壮烈"],
            "悬疑": ["悬疑", "神秘", "阴影", "暗处"],
            "热血": ["热血", "怒吼", "爆发", "冲"],
            "宁静": ["宁静", "安静", "平和", "缓缓"],
            "恐怖": ["阴森", "恐怖", "诡异", "黑暗"],
            "浪漫": ["浪漫", "深情", "凝视", "靠近"],
        }

        text_lower = text.lower() if text else ""
        for atmosphere, keywords in atmosphere_keywords.items():
            if any(kw in text for kw in keywords):  # Use original text not lower for Chinese
                return atmosphere

        return "中性"

    def _extract_time_of_day(self, text: str) -> str:
        """Extract time of day from text."""
        time_keywords = {
            "清晨": ["清晨", "黎明", "天亮", "朝阳"],
            "正午": ["正午", "中午", "烈日", "当空"],
            "黄昏": ["黄昏", "傍晚", "夕阳", "日落"],
            "夜晚": ["夜晚", "深夜", "黑夜", "月光", "星空", "夜幕"],
        }

        for time_of_day, keywords in time_keywords.items():
            if any(kw in text for kw in keywords):
                return time_of_day

        return "未指定"

    def _extract_weather(self, text: str) -> str:
        """Extract weather from text."""
        weather_keywords = {
            "晴": ["晴", "阳光", "明媚"],
            "雨": ["雨", "雨滴", "暴雨", "细雨"],
            "雪": ["雪", "雪花", "大雪", "飘雪"],
            "雾": ["雾", "薄雾", "浓雾"],
            "风": ["风", "狂风", "微风", "暴风"],
            "阴": ["阴天", "乌云", "阴沉"],
        }

        for weather, keywords in weather_keywords.items():
            if any(kw in text for kw in keywords):
                return weather

        return "晴"

    def _extract_scene_elements(self, text: str) -> List[str]:
        """Extract key scene elements/objects from text."""
        common_elements = [
            "桌子", "椅子", "窗户", "门", "灯", "书架",
            "床", "沙发", "柜子", "镜子", "楼梯", "走廊",
            "树", "花", "草", "石头", "山", "河", "湖", "海",
            "建筑", "街道", "广场", "房间", "大厅", "宫殿",
            "剑", "刀", "枪", "弓", "盾",
        ]

        found: List[str] = []
        for element in common_elements:
            if element in text:
                found.append(element)

        return list(dict.fromkeys(found))  # Deduplicate

    def _generate_six_grid(
        self,
        text: str,
        character_list: List[str],
    ) -> List[SceneFrame]:
        """Generate 6 key frames from scene text.

        Divides scene by rhythm breakpoints (sentence boundaries)
        into 6 representative key frames.
        """
        frames: List[SceneFrame] = []

        # Split text into segments
        segments = self._split_by_rhythm(text)

        # Select 6 key segments
        key_segments = self._select_key_segments(segments, self.GRID_FRAMES)

        for i, seg in enumerate(key_segments):
            frame = SceneFrame(
                frame_id=i + 1,
                description=seg[:200],  # Truncate
                key_action=self._extract_key_action(seg, character_list),
                composition_hint=self._suggest_composition(i, self.GRID_FRAMES),
                emotional_peak=self._estimate_emotional_peak(seg),
            )
            frames.append(frame)

        # Pad to 6 if needed
        while len(frames) < self.GRID_FRAMES:
            frames.append(SceneFrame(
                frame_id=len(frames) + 1,
                description="(过渡画面)",
                key_action="场景转换",
                composition_hint="过渡",
                emotional_peak=0.3,
            ))

        return frames[:self.GRID_FRAMES]

    def _split_by_rhythm(self, text: str) -> List[str]:
        """Split text by rhythm breakpoints (sentence boundaries)."""
        import re
        # Split by Chinese punctuation marks
        segments = re.split(r"[。！？；\n，]", text)
        return [s.strip() for s in segments if s.strip()]

    def _select_key_segments(self, segments: List[str], count: int) -> List[str]:
        """Select evenly distributed key segments."""
        if not segments:
            return [""] * count
        if len(segments) <= count:
            return segments

        # Evenly sample
        step = len(segments) / count
        indices = [int(i * step) for i in range(count)]
        return [segments[i] for i in indices if i < len(segments)]

    def _extract_key_action(self, text: str, character_list: List[str]) -> str:
        """Extract key action from segment."""
        # Check if any character name appears
        for char in character_list:
            if char in text:
                return f"{char}相关动作"

        if not text:
            return "场景描述"
        return text[:50] + ("..." if len(text) > 50 else "")

    def _suggest_composition(self, index: int, total: int) -> str:
        """Suggest composition based on position in the sequence."""
        compositions = [
            "全景建立场景",
            "中景引入角色",
            "近景展现互动",
            "特写强调关键",
            "中景推动剧情",
            "全景收束场景",
        ]
        if index < len(compositions):
            return compositions[index]
        return "中景"

    def _estimate_emotional_peak(self, text: str) -> float:
        """Estimate emotional intensity of text segment."""
        intense_words = ["怒", "吼", "哭", "笑", "惊", "恐", "急", "冲", "杀", "爆"]
        calm_words = ["静", "缓", "轻", "慢", "柔", "淡"]

        score = 0.5
        for word in intense_words:
            if word in text:
                score += 0.1
        for word in calm_words:
            if word in text:
                score -= 0.05

        return max(0.0, min(1.0, score))

    def _generate_tags(self, dna: SceneDNAEnhanced) -> List[str]:
        """Generate environment/style tags."""
        tags: List[str] = []

        if dna.atmosphere and dna.atmosphere != "中性":
            tags.append(f"{dna.atmosphere}氛围")

        if dna.time_of_day and dna.time_of_day != "未指定":
            tags.append(dna.time_of_day)

        if dna.weather and dna.weather != "晴":
            tags.append(f"{dna.weather}天")

        tags.append("动漫风格")
        tags.append("高细节背景")

        return tags
