"""Story text parser — extract chapters, scenes, shots from prose.

Sprint 8.0: Added Chinese NLP layer integration. When text is primarily Chinese,
routes to ChineseSceneParser for segmentation; CharacterExtractor uses ChineseExtractor.
"""

from __future__ import annotations

import re
from typing import Optional

from backend.story.models import Chapter, Scene, Shot


def _is_chinese_text(text: str) -> bool:
    """Detect if text is primarily Chinese by CJK character ratio."""
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    total = len(text.strip()) or 1
    return cjk / total > 0.3


class StoryParser:
    """Parses novel text into Chapter → Scene → Shot hierarchy.
    Automatically routes Chinese text to NLP layer (Sprint 8.0)."""

    # Patterns for structural boundaries
    CHAPTER_PATTERN = re.compile(
        r'(?:第[一二三四五六七八九十百千\d]+[章节]|Chapter\s+\d+|CH\.\s*\d+|^\d+[\.\、]?\s+[^\n]+)',
        re.MULTILINE | re.IGNORECASE,
    )
    SCENE_BREAK = re.compile(r'\n(?:---|\*\s*\*\s*\*|___|···)\n|\n{3,}')
    DIALOGUE_PATTERN = re.compile(r'[""]([^"""]+)[""]|「([^」]+)」')

    def parse_full(self, text: str, novel_id: str = "") -> list[Chapter]:
        """Parse full novel text into chapters with scenes."""
        return [chapter for chapter, _scene_data in self.parse_hierarchy(text, novel_id)]

    def parse_hierarchy(
        self, text: str, novel_id: str = ""
    ) -> list[tuple[Chapter, list[tuple[Scene, list[Shot]]]]]:
        """Parse text once into the canonical chapter → scene → shot hierarchy."""
        chapter_texts = self._split_chapters(text)
        hierarchy: list[tuple[Chapter, list[tuple[Scene, list[Shot]]]]] = []

        for i, ch_text in enumerate(chapter_texts):
            chapter = Chapter(
                novel_id=novel_id,
                number=i + 1,
                title=self._extract_chapter_title(ch_text),
                raw_text=ch_text,
                word_count=len(ch_text),
            )
            scenes = self._split_scenes(ch_text, chapter.id)
            scene_data: list[tuple[Scene, list[Shot]]] = []
            for scene in scenes:
                shots = self._extract_shots(scene.raw_text, scene.id)
                scene.shots = [shot.id for shot in shots]
                scene_data.append((scene, shots))
            chapter.scenes = [s.id for s in scenes]
            hierarchy.append((chapter, scene_data))

        return hierarchy

    def parse_chapter(self, text: str, chapter_id: str = "", number: int = 1) -> Chapter:
        """Parse a single chapter text into scenes and shots."""
        chapter = Chapter(
            chapter_id=chapter_id if chapter_id else "",
            number=number,
            title=self._extract_chapter_title(text),
            raw_text=text,
            word_count=len(text),
        )
        return chapter

    def parse_single_text(self, text: str, novel_id: str = "") -> dict:
        """Parse any text into structured scene data. Returns dict with scenes and shots."""
        scenes = self._split_scenes(text, "")
        result = {
            "scenes": [],
        }
        for s in scenes:
            shots = self._extract_shots(s.raw_text, s.id)
            s.shots = [sh.id for sh in shots]
            result["scenes"].append({
                "scene": s,
                "shots": shots,
            })
        return result

    # ── Internal ──

    def _split_chapters(self, text: str) -> list[str]:
        """Split raw novel text into chapter blocks."""
        chapters = []
        lines = text.split("\n")
        current: list[str] = []
        chapter_count = 0

        for line in lines:
            if self.CHAPTER_PATTERN.match(line.strip()) and chapter_count > 0:
                chapters.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
            if self.CHAPTER_PATTERN.match(line.strip()):
                chapter_count += 1

        if current:
            chapters.append("\n".join(current))

        return chapters if chapters else [text]

    def _extract_chapter_title(self, text: str) -> str:
        """Extract chapter title from first line."""
        first_line = text.strip().split("\n")[0]
        match = self.CHAPTER_PATTERN.match(first_line)
        if match:
            return first_line[:80]
        return f"第 {len(text.split()) // 2000 + 1} 章"

    def _split_scenes(self, text: str, chapter_id: str) -> list[Scene]:
        """Split chapter text into scenes. Routes Chinese text to NLP layer."""
        if _is_chinese_text(text):
            return self._split_scenes_zh(text, chapter_id)

        parts = self.SCENE_BREAK.split(text)
        scenes: list[Scene] = []

        for i, part in enumerate(parts):
            part = part.strip()
            if not part or len(part) < 20:
                continue

            scene = Scene(
                chapter_id=chapter_id,
                number=i + 1,
                raw_text=part,
                mood=self._detect_mood(part),
                characters=self._extract_character_mentions(part),
            )
            scenes.append(scene)

        return scenes

    def _split_scenes_zh(self, text: str, chapter_id: str) -> list[Scene]:
        """Chinese-optimized scene splitting via NLP layer (Sprint 8.0)."""
        from backend.nlp.chinese_segmenter import ChineseSceneParser

        zh_parser = ChineseSceneParser()
        zh_scenes = zh_parser.parse_scenes(text)
        scenes: list[Scene] = []

        for zs in zh_scenes:
            scene = Scene(
                chapter_id=chapter_id,
                number=zs.index,
                raw_text=zs.raw_text,
                mood=zs.mood,
                characters=zs.characters_mentioned,
            )
            scenes.append(scene)

        return scenes

    @staticmethod
    def _extract_action_cn(text: str) -> str:
        """Extract key action from Chinese sentence."""
        action_kw = ["站", "走", "跑", "跳", "飞", "落", "倒", "抓", "握", "抱",
                     "拔", "斩", "砍", "刺", "劈", "射", "挥", "打", "击", "推",
                     "拉", "抬", "低", "转", "回", "冲", "闯", "踏", "跃", "降",
                     "施法", "凝聚", "释放", "召唤", "变身", "怒吼", "咆哮", "颤抖"]
        found = [kw for kw in action_kw if kw in text]
        return found[0] if found else ""

    def _extract_shots(self, text: str, scene_id: str) -> list[Shot]:
        """Parse a scene into visual shots based on paragraph breaks and action markers.
        Routes Chinese text to NLP layer (Sprint 8.0)."""
        if _is_chinese_text(text):
            from backend.nlp.chinese_segmenter import ChineseSceneParser
            from backend.nlp.chinese_ner import ChineseExtractor
            zh_parser = ChineseSceneParser()
            ner = ChineseExtractor()
            all_names = ner.extract_names(text)
            zh_shots = zh_parser.extract_shots(text, scene_id)
            result = []
            for zs in zh_shots:
                desc = zs["description"]
                shot_chars = [n for n in all_names if n in desc]
                result.append(Shot(
                    scene_id=scene_id,
                    index=zs["index"],
                    description=desc,
                    shot_type=zs["shot_type"],
                    camera_angle=zs.get("camera_angle", "eye-level"),
                    emotion=zs.get("emotion", "neutral"),
                    character_ids=shot_chars,
                    action=self._extract_action_cn(desc),
                    dialogue="yes" if any(kw in desc for kw in ["说", "道", "喊", "问", "答"]) else "",
                ))
            return result

        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        shots: list[Shot] = []

        for i, para in enumerate(paragraphs):
            if len(para) < 30:
                continue

            shot = Shot(
                scene_id=scene_id,
                index=i,
                description=para[:200],
                shot_type=self._infer_shot_type(para),
                camera_angle=self._infer_camera_angle(para),
                dialogue=self._extract_dialogue(para),
                emotion=self._detect_mood(para),
            )
            shots.append(shot)

        return shots

    def _extract_dialogue(self, text: str) -> str:
        """Extract dialogue from text."""
        matches = self.DIALOGUE_PATTERN.findall(text)
        dialogues = [m[0] or m[1] for m in matches]
        return " | ".join(dialogues) if dialogues else ""

    @staticmethod
    def _detect_mood(text: str) -> str:
        """Heuristic mood detection."""
        text_lower = text.lower()
        moods = {
            "tense": ["tense", "nervous", "anxious", "fear", "danger", "threat", "attack"],
            "calm": ["calm", "peaceful", "quiet", "serene", "soft"],
            "dramatic": ["dramatic", "intense", "explosive", "thunder", "roar"],
            "dark": ["dark", "shadow", "gloom", "sinister", "evil", "bleak"],
            "hopeful": ["hope", "light", "bright", "warm", "smile", "laugh"],
            "comedic": ["funny", "laugh", "joke", "ridiculous", "absurd", "silly"],
        }
        scores = {m: sum(k in text_lower for k in kw) for m, kw in moods.items()}
        if max(scores.values()) > 0:
            return max(scores, key=scores.get)
        return "neutral"

    @staticmethod
    def _infer_shot_type(text: str) -> str:
        """Infer cinematic shot type from description."""
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["extreme close", "zoom in", "detail of", "close up of"]):
            return "extreme-close-up"
        if any(kw in text_lower for kw in ["close up", "face", "expression", "eyes"]):
            return "close-up"
        if any(kw in text_lower for kw in ["wide shot", "landscape", "vista", "overview", "cityscape"]):
            return "wide"
        if any(kw in text_lower for kw in ["panorama", "skyline", "horizon"]):
            return "panorama"
        if any(kw in text_lower for kw in ["long shot", "distance", "far away"]):
            return "long"
        return "medium"

    @staticmethod
    def _infer_camera_angle(text: str) -> str:
        """Infer camera angle from description."""
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["looking up", "towering", "above"]):
            return "low-angle"
        if any(kw in text_lower for kw in ["looking down", "below", "bird", "aerial"]):
            return "high-angle"
        if any(kw in text_lower for kw in ["tilted", "skewed", "dutch"]):
            return "dutch"
        return "eye-level"

    @staticmethod
    def _extract_character_mentions(text: str) -> list[str]:
        """Extract capitalized names as potential character mentions."""
        name_pattern = re.compile(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)\b')
        names = name_pattern.findall(text)
        stop_words = {"the", "and", "but", "that", "with", "from", "this", "they", "their", "them", "then", "when", "where", "what", "which", "there", "here", "been"}
        return list(set(n for n in names if n.lower() not in stop_words))
