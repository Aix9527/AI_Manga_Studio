"""Chinese scene segmentation — chapter boundary detection, paragraph grouping, transition word boundary markers.

Replaces English-biased _split_scenes with Chinese-aware splitting:
1. Chapter markers: 第X章, 第X话, Chapter X
2. Scene transition words: 突然, 此时, 另一边, 第二天, etc.
3. Paragraph gap grouping: merge short paragraphs, split on major scene breaks
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ChineseScene:
    """A parsed scene segment from Chinese prose."""
    index: int
    raw_text: str
    word_count: int
    mood: str = "neutral"
    location_hint: str = ""
    characters_mentioned: list[str] = field(default_factory=list)
    transition_marker: str = ""   # which scene marker triggered the split


class ChineseSceneParser:
    """Chinese-optimized scene parser for novel text."""

    # Chinese chapter markers
    CHAPTER_PATTERNS = [
        re.compile(r'第[一二三四五六七八九十百千\d]+[章节话卷]'),   # 第一章, 第三话
        re.compile(r'^[#＃]\s*\d+'),                              # #1, ＃2
        re.compile(r'Chapter\s+\d+', re.IGNORECASE),               # English fallback
    ]

    # Scene transition keywords — these indicate a new scene has started
    SCENE_TRANSITION_MARKERS: list[str] = [
        "突然", "忽然", "骤然",
        "此时", "此刻", "与此同时",
        "另一边", "另一方", "镜头转向",
        "第二天", "次日", "翌日", "几日后", "数日后",
        "夜晚", "清晨", "黄昏", "深夜", "黎明", "午后",
        "多年以后", "数月之后", "三年后",
        "话说", "却说", "且说",
        "——", "场景转换",
    ]

    # Location keywords for scene setting detection
    LOCATION_KEYWORDS: dict[str, list[str]] = {
        "indoor": ["室内", "房间", "大厅", "宫殿", "卧室", "客厅", "书房", "厨房"],
        "outdoor": ["户外", "野外", "森林", "沙漠", "山脉", "草原", "海岸"],
        "urban": ["城市", "街道", "广场", "市场", "城楼", "城墙"],
        "battlefield": ["战场", "擂台", "竞技场", "决斗场"],
        "mystical": ["秘境", "洞窟", "遗迹", "禁地", "圣殿"],
        "school": ["学院", "宗门", "道观", "寺庙"],
        "night_sky": ["夜空", "星空", "星域", "天际"],
    }

    def parse_scenes(self, text: str) -> list[ChineseScene]:
        """Parse text into a list of ChineseScene objects."""
        # Step 1: split by chapters first
        chapter_blocks = self._split_chapters(text)

        # Step 2: within each chapter, split by scene boundaries
        scenes: list[ChineseScene] = []
        scene_idx = 0

        for ch_block in chapter_blocks:
            sub_scenes = self._split_into_scenes(ch_block)
            for raw in sub_scenes:
                if len(raw.strip()) < 20:
                    continue
                scene_idx += 1
                scene = ChineseScene(
                    index=scene_idx,
                    raw_text=raw.strip(),
                    word_count=len(raw),
                    mood=self._detect_mood(raw),
                    location_hint=self._detect_location(raw),
                    characters_mentioned=self._extract_entity_mentions(raw),
                )
                scenes.append(scene)

        return scenes

    def parse_single_text(self, text: str) -> str:
        """Return segmented text with scene markers for debugging."""
        scenes = self.parse_scenes(text)
        output = []
        for s in scenes:
            output.append(f"=== Scene {s.index} ({s.word_count}字, mood={s.mood}) ===")
            if s.location_hint:
                output.append(f"  Location: {s.location_hint}")
            if s.characters_mentioned:
                output.append(f"  Characters: {', '.join(s.characters_mentioned)}")
            output.append(s.raw_text[:200] + ("..." if len(s.raw_text) > 200 else ""))
            output.append("")
        return "\n".join(output)

    def get_scene_data(self, text: str) -> list[dict]:
        """Return list of dicts for pipeline consumption."""
        scenes = self.parse_scenes(text)
        return [
            {
                "index": s.index,
                "text": s.raw_text,
                "word_count": s.word_count,
                "mood": s.mood,
                "location": s.location_hint,
                "characters": s.characters_mentioned,
            }
            for s in scenes
        ]

    # ── Internal ──

    def _split_chapters(self, text: str) -> list[str]:
        """Split text into chapter blocks using Chinese patterns."""
        lines = text.split("\n")
        chapters: list[list[str]] = []
        current: list[str] = []

        for line in lines:
            stripped = line.strip()
            is_chapter_start = any(p.search(stripped) for p in self.CHAPTER_PATTERNS)

            if is_chapter_start and current and len("\n".join(current).strip()) > 50:
                chapters.append(current)
                current = [line]
            else:
                current.append(line)

        if current:
            chapters.append(current)

        result = ["\n".join(ch) for ch in chapters]
        # If no chapters detected, treat whole text as one block
        return result if result else [text]

    def _split_into_scenes(self, text: str) -> list[str]:
        """Split a chapter block into individual scenes.

        Three strategies combined:
        1. Transition marker at paragraph start (突然, 此时, 第二天, etc.)
        2. Double newline gaps (paragraph gaps ≥ 2 blank lines)
        3. Topic shift detection via paragraph length jump + mood change
        """
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        if not paragraphs:
            return [text]

        # Alongside paragraphs, track which lines were blank
        raw_lines = text.split("\n")
        gap_map: list[int] = []  # consecutive blank lines before each non-blank para
        blank_count = 0
        for line in raw_lines:
            if not line.strip():
                blank_count += 1
            else:
                gap_map.append(blank_count)
                blank_count = 0

        scenes: list[list[str]] = []
        current_scene: list[str] = []

        for i, para in enumerate(paragraphs):
            is_new_scene = False

            # Strategy 1: transition marker at paragraph start
            for marker in self.SCENE_TRANSITION_MARKERS:
                if para.startswith(marker):
                    is_new_scene = True
                    break

            # Strategy 2: significant paragraph gap (≥ 3 blank lines)
            if not is_new_scene and i < len(gap_map) and gap_map[i] >= 3:
                is_new_scene = True

            # Strategy 3: mood shift in adjacent paragraphs
            if not is_new_scene and i > 0 and current_scene:
                prev_mood = self._detect_mood("\n".join(current_scene[-2:]) if len(current_scene) >= 2 else current_scene[-1])
                curr_mood = self._detect_mood(para)
                if prev_mood != "neutral" and curr_mood != "neutral" and prev_mood != curr_mood:
                    is_new_scene = True

            if is_new_scene and current_scene:
                scenes.append(current_scene)
                current_scene = [para]
            else:
                current_scene.append(para)

        if current_scene:
            scenes.append(current_scene)

        # Merge very short scenes (< 30 chars) with previous
        merged: list[str] = []
        for scene_paras in scenes:
            combined = "\n".join(scene_paras)
            if len(combined) < 30 and merged:
                merged[-1] = merged[-1] + "\n" + combined
            else:
                merged.append(combined)

        return merged

    def _detect_mood(self, text: str) -> str:
        """Detect the dominant mood of a scene using Chinese keywords."""
        mood_map: dict[str, list[str]] = {
            "tense": ["紧张", "危机", "危险", "攻击", "战斗", "威胁", "压迫"],
            "calm": ["平静", "安静", "宁静", "祥和", "悠然", "闲适"],
            "dramatic": ["激烈", "震撼", "爆裂", "怒吼", "轰鸣", "爆发"],
            "dark": ["黑暗", "阴影", "阴森", "邪恶", "绝望", "冰冷", "深渊"],
            "sad": ["悲伤", "痛苦", "流泪", "哀伤", "凄凉", "心碎"],
            "hopeful": ["希望", "光明", "温暖", "微笑", "曙光", "新生"],
            "romantic": ["温柔", "深情", "凝视", "拥抱", "心动"],
            "epic": ["宏大", "壮阔", "星辰", "天地", "苍穹", "万古"],
        }

        scores: dict[str, int] = {}
        for mood, keywords in mood_map.items():
            scores[mood] = sum(text.count(kw) for kw in keywords)

        if max(scores.values()) > 0:
            return max(scores, key=scores.get)
        return "neutral"

    def _detect_location(self, text: str) -> str:
        """Detect scene location/setting from keywords."""
        for loc_type, keywords in self.LOCATION_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    return loc_type
        return ""

    def _extract_entity_mentions(self, text: str) -> list[str]:
        """Quick extraction of potential character mentions using Chinese patterns."""
        import jieba as _jieba
        surnames = "林苏王张刘陈杨赵黄周吴徐孙胡朱高何郭马罗梁宋郑谢韩唐冯于叶萧程曹袁邓许傅沈曾彭吕卢蒋蔡贾丁魏薛"
        surname_set = set(surnames)
        # Fallback: scan for surname + 1-2 char patterns
        mentions: list[str] = []
        for i, ch in enumerate(text):
            if ch in surname_set and i + 1 < len(text):
                if '\u4e00' <= text[i + 1] <= '\u9fff':
                    name = text[i:i + 2]
                    if i + 2 < len(text) and '\u4e00' <= text[i + 2] <= '\u9fff':
                        name = text[i:i + 3]  # rare 3-char names
                    mentions.append(name)
        return list(set(mentions))[:20]

    # ── Shot extraction ──

    def extract_shots(self, scene_text: str, scene_id: str = "") -> list[dict]:
        """Split a scene into cinematic shot candidates."""
        paragraphs = [p.strip() for p in scene_text.split("\n") if p.strip()]
        shots = []

        for i, para in enumerate(paragraphs):
            if len(para) < 15:
                continue

            shot = {
                "index": i,
                "scene_id": scene_id,
                "description": para[:200],
                "shot_type": self._infer_shot_type(para),
                "camera_angle": self._infer_shot_angle(para),
                "emotion": self._detect_mood(para),
                "word_count": len(para),
            }
            shots.append(shot)

        return shots

    @staticmethod
    def _infer_shot_type(text: str) -> str:
        """Infer shot type from Chinese descriptors."""
        if any(kw in text for kw in ["特写", "近景", "细节", "双眼", "面容"]):
            return "close-up"
        if any(kw in text for kw in ["远景", "全景", "俯瞰", "远眺"]):
            return "wide"
        if any(kw in text for kw in ["中景", "半身"]):
            return "medium"
        if any(kw in text for kw in ["仰视", "仰望", "抬头看"]):
            return "low-angle"
        if any(kw in text for kw in ["俯视", "鸟瞰", "俯瞰"]):
            return "high-angle"
        return "medium"

    @staticmethod
    def _infer_shot_angle(text: str) -> str:
        """Infer camera angle from Chinese descriptors."""
        if any(kw in text for kw in ["仰视", "仰望", "抬头看", "高耸"]):
            return "low-angle"
        if any(kw in text for kw in ["俯视", "鸟瞰", "俯瞰", "向下看"]):
            return "high-angle"
        if any(kw in text for kw in ["倾斜", "歪斜"]):
            return "dutch"
        return "eye-level"


