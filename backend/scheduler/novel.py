"""
Scheduler — Novel Parsing

Stage 1: Read novel text → split chapters → extract scenes/shots → save JSON to disk.

Uses the existing AIDirector for parsing intelligence, then serializes
everything into UnifiedShot JSON files under the project output directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from loguru import logger

from backend.ai_director import AIDirector, ShotDirective
from backend.unified_shot import UnifiedShot, ShotBatch
from backend.config import get_config
from backend.script_parser import ScriptParser, StructuredShot, StructuredChapter, StructuredScript


# ============================================================
# Output types
# ============================================================

@dataclass
class NovelParseResult:
    """What comes out of novel parsing — passed to downstream stages."""
    project_id: str
    chapters: List[ChapterParsed] = field(default_factory=list)
    total_shots: int = 0
    total_chapters: int = 0


@dataclass
class ChapterParsed:
    """A parsed chapter ready for generation."""
    index: int
    title: str = ""
    shot_files: List[str] = field(default_factory=list)  # paths to shot JSONs


# ============================================================
# Stage: Novel Parsing
# ============================================================

class NovelStage:
    """Read novel → chapters → shots → UnifiedShot JSON.

    This stage owns the AIDirector and writes the output that
    every downstream stage reads.
    """

    def __init__(self, project_dir: str = ""):
        cfg = get_config()
        self.base_dir = Path(project_dir or cfg.project.output_path or cfg.project.root_path)
        self.director = AIDirector()

    def parse(self, novel_path: str, project_id: str = "", max_shots_per_chapter: int = 30) -> NovelParseResult:
        """Parse a novel file into chapters and shots.

        Args:
            novel_path: Absolute path to .txt novel file.
            project_id: Project identifier (folder name).
            max_shots_per_chapter: Upper limit on shots per chapter.

        Returns:
            NovelParseResult with chapter/shot structure.
        """
        pid = project_id or Path(novel_path).stem
        logger.info(f"NovelStage: Parsing '{novel_path}' → project '{pid}'")

        # Load full text
        self.director.load_novel(novel_path)
        full_text = self.director.novel_text

        # ── Tier 0: ScriptParser for structured scripts ──
        try:
            parser = ScriptParser()
            script = parser.parse(full_text)
            if script.chapters and any(ch.shots for ch in script.chapters):
                logger.info(
                    f"NovelStage: ScriptParser detected {len(script.chapters)} chapters, "
                    f"{script.total_shots} total shots"
                )
                return self._parse_from_script(script, pid, max_shots_per_chapter)
        except Exception as e:
            logger.debug(f"NovelStage: ScriptParser skipped ({e}), falling back")

        # ── Fallback: AIDirector chapter segmentation ──
        chapters = self.director.segment_chapters()

        # Extract characters, scenes and shots from the full novel
        try:
            self.director.extract_characters()
            self.director.identify_scenes()
            self.director.plan_shots()
            logger.info(
                f"NovelStage: AI Director — {len(self.director.characters)} characters, "
                f"{len(self.director.scenes)} scenes, "
                f"{len(self.director.shots)} shots"
            )
        except Exception as e:
            logger.warning(f"NovelStage: AI analysis skipped: {e}")

        result = NovelParseResult(project_id=pid, total_chapters=len(chapters))

        # Process each chapter
        for ch_idx, ch_text in enumerate(chapters):
            ch_result = self._parse_chapter(ch_idx, ch_text, pid, max_shots_per_chapter)
            result.chapters.append(ch_result)
            result.total_shots += len(ch_result.shot_files)

        logger.info(
            f"NovelStage: Done — {result.total_chapters} chapters, "
            f"{result.total_shots} shots"
        )
        return result

    def _parse_from_script(
        self,
        script: StructuredScript,
        project_id: str,
        max_shots_per_chapter: int,
    ) -> NovelParseResult:
        """Parse from ScriptParser output directly — full structured control."""
        result = NovelParseResult(
            project_id=project_id,
            total_chapters=len(script.chapters),
        )

        for ch_idx, chapter in enumerate(script.chapters):
            if not chapter.shots:
                continue

            ch_result = ChapterParsed(index=ch_idx + 1, title=chapter.title)

            # Write each shot as UnifiedShot JSON
            chapter_dir = self.base_dir / project_id / f"ch{ch_idx + 1:02d}" / "shots"
            chapter_dir.mkdir(parents=True, exist_ok=True)

            for si, ss in enumerate(chapter.shots[:max_shots_per_chapter]):
                characters = ss.characters_present or []

                # Map time_of_day to valid enum values
                tod = ss.time_of_day or "noon"
                TOD_MAP = {
                    "day": "noon", "白天": "noon", "日": "noon",
                    "night": "night", "夜": "night", "夜间": "night", "夜晚": "night",
                    "dawn": "dawn", "清晨": "dawn", "早晨": "dawn", "早上": "dawn",
                    "dusk": "dusk", "黄昏": "dusk", "傍晚": "dusk",
                    "morning": "morning", "上午": "morning",
                    "afternoon": "afternoon", "下午": "afternoon",
                }
                tod = TOD_MAP.get(tod, "noon")

                shot = UnifiedShot(
                    chapter=ch_idx + 1,
                    scene=1,
                    shot=si + 1,
                    duration=ss.duration,
                    characters=characters,
                    character_details=[],
                    background=ss.location or "",
                    foreground="",
                    composition_notes=ss.scene_description or ss.action or "",
                    emotion=ss.emotion or "neutral",
                    atmosphere="",
                    color_palette="",
                    lighting="natural",
                    weather="clear",
                    time_of_day=tod,
                    light_source="",
                    voice="",
                    dialogue=ss.dialogue or "",
                    sfx=ss.sfx or "",
                    bgm=ss.bgm or "",
                    seed=-1,
                    steps=30,
                    cfg=7.0,
                    width=1920,
                    height=1080,
                    negative_prompt="",
                    extra={
                        "camera": ss.camera,
                        "camera_angle": ss.camera_angle or "",
                        "camera_motion": ss.camera_motion or "",
                        "interior_exterior": ss.interior_exterior,
                        "vfx": ss.vfx or "",
                    } if (ss.camera_angle or ss.camera_motion or ss.vfx) else {},
                    status="waiting",
                )

                shot_path = str(chapter_dir / f"shot_{si + 1:03d}.json")
                shot.to_json_file(shot_path)
                ch_result.shot_files.append(shot_path)

            result.chapters.append(ch_result)
            result.total_shots += len(ch_result.shot_files)
            logger.info(
                f"NovelStage: ch{ch_idx + 1:02d} '{chapter.title}' → "
                f"{len(chapter.shots)} shots"
            )

        return result

    def _parse_chapter(
        self,
        ch_idx: int,
        ch_text: str,
        project_id: str,
        max_shots: int,
    ) -> ChapterParsed:
        """Parse a single chapter into shots and write JSONs."""
        chapter = ChapterParsed(index=ch_idx + 1)

        # Extract shots from chapter text
        shots = self._extract_shots_from_text(ch_text, ch_idx, max_shots)

        # Write each shot as UnifiedShot JSON
        chapter_dir = self.base_dir / project_id / f"ch{ch_idx + 1:02d}" / "shots"
        chapter_dir.mkdir(parents=True, exist_ok=True)

        for si, shot_directive in enumerate(shots):
            # Characters: normalize to list
            chars = shot_directive.characters_present or []
            if isinstance(chars, str):
                chars = [chars]

            # Duration
            dur = getattr(shot_directive, "duration", 3.0)
            if isinstance(dur, (int, float)):
                dur = max(1.5, float(dur))
            else:
                dur = 3.0

            # Extra fields from structured parse
            extra = getattr(shot_directive, "extra", {}) or {}

            shot = UnifiedShot(
                chapter=ch_idx + 1,
                scene=1,
                shot=si + 1,
                duration=dur,

                characters=chars,
                background=shot_directive.scene_name or extra.get("scene_name", ""),
                dialogue=shot_directive.dialogue or "",
                narration=shot_directive.narration or shot_directive.action or "",
                emotion=self._map_emotion(getattr(shot_directive, "emotion", "neutral")),
                camera=self._map_camera(getattr(shot_directive, "camera", "medium")),
                camera_angle=extra.get("camera_angle", ""),
                camera_motion=extra.get("camera_motion", ""),
                time_of_day=extra.get("time_of_day", "noon"),
                sfx=extra.get("sfx", ""),
                bgm=extra.get("bgm", ""),
                composition_notes=shot_directive.narration or shot_directive.action or "",
            )

            shot_path = str(chapter_dir / f"shot_{si + 1:03d}.json")
            shot.to_json_file(shot_path)
            chapter.shot_files.append(shot_path)

        logger.info(f"NovelStage: ch{ch_idx + 1:02d} → {len(shots)} shots")
        return chapter

    def _extract_shots_from_text(
        self,
        ch_text: str,
        ch_idx: int,
        max_shots: int,
    ) -> List[ShotDirective]:
        """Extract shot directives from chapter text.

        Priority:
          1. ScriptParser — for pre-structured scripts (X.txt format)
          2. AIDirector — LLM-based intelligence
          3. Paragraph fallback — raw text split
        """
        shots: List[ShotDirective] = []

        # --- Tier 1: ScriptParser for structured scripts ---
        try:
            parser = ScriptParser()
            parsed = parser.parse(ch_text)
            if parsed.chapters and any(ch.shots for ch in parsed.chapters):
                logger.info(f"NovelStage: ScriptParser detected {parsed.total_shots} structured shots in {len(parsed.chapters)} chapters")
                return self._convert_structured_shots(parsed, ch_idx, max_shots)
        except Exception as e:
            logger.debug(f"NovelStage: ScriptParser skipped ({e}), trying AIDirector")

        # --- Tier 2: AIDirector (pre-computed in parse()) ---
        if self.director.shots:
            for s in self.director.shots:
                if s.chapter_index == ch_idx + 1:  # AIDirector uses 1-based chapter_index
                    shots.append(s)
            if shots:
                return shots[:max_shots]

        # --- Tier 3: Raw paragraph fallback ---
        paragraphs = [p.strip() for p in ch_text.split("\n") if p.strip()]
        for si, para in enumerate(paragraphs[:max_shots]):
            shot = ShotDirective(
                index=si,
                chapter_index=ch_idx,
                action=para[:200],
            )
            import re as _re
            dialogue = _re.findall(r'[「『""]([^」』""]+)[」』""]', para)
            if dialogue:
                shot.dialogue = " ".join(dialogue)
            shots.append(shot)

        return shots

    def _convert_structured_shots(
        self,
        script: StructuredScript,
        ch_idx: int,
        max_shots: int,
    ) -> List[ShotDirective]:
        """Convert ScriptParser output back to ShotDirective format.

        Since ScriptParser may skip empty chapters (prologue), we match
        chapters by sequential order: the Nth non-empty chapter maps to ch_idx.
        """
        shots: List[ShotDirective] = []
        non_empty_chapters = [ch for ch in script.chapters if ch.shots]

        if not non_empty_chapters:
            return shots

        # When called per-chapter (AIDirector already segmented), use
        # the single chapter directly regardless of ch_idx.
        # When called with full text, match by sequential index.
        if len(non_empty_chapters) == 1:
            chapter = non_empty_chapters[0]
        elif ch_idx < len(non_empty_chapters):
            chapter = non_empty_chapters[ch_idx]
        else:
            return shots

        for ss in chapter.shots[:max_shots]:
            sd = ShotDirective(
                index=ss.index,
                chapter_index=ch_idx,
                scene_name=ss.location,
                action=ss.action or ss.scene_description,
                dialogue=ss.dialogue,
                characters_present=ss.characters_present,
                camera=ss.camera,
                emotion=ss.emotion or "neutral",
                duration=ss.duration,
                narration=ss.scene_description,
            )

            # Carry through structured extras via the directive
            if ss.time_of_day:
                sd.extra = getattr(sd, "extra", {}) or {}
                sd.extra["time_of_day"] = ss.time_of_day
            if ss.camera_angle:
                sd.extra = sd.extra or {}
                sd.extra["camera_angle"] = ss.camera_angle
            if ss.camera_motion:
                sd.extra = sd.extra or {}
                sd.extra["camera_motion"] = ss.camera_motion
            if ss.sfx:
                sd.extra = sd.extra or {}
                sd.extra["sfx"] = ss.sfx
            if ss.bgm:
                sd.extra = sd.extra or {}
                sd.extra["bgm"] = ss.bgm

            shots.append(sd)

        return shots

    @staticmethod
    def _map_emotion(raw: str) -> str:
        mapping = {
            "anger": "angry", "joy": "happy", "sadness": "sad",
            "fear": "fearful", "surprise": "surprised", "calm": "calm",
        }
        return mapping.get(raw.lower(), "neutral")

    @staticmethod
    def _map_camera(raw: str) -> str:
        raw_lower = raw.lower()
        # Map AIDirector camera instructions to Camera enum
        for keyword, mapped in [
            ("close-up", "close"), ("close", "close"), ("closeup", "close"),
            ("medium", "medium"), ("mid", "medium"),
            ("wide", "wide"), ("full", "wide"),
            ("drone", "drone"), ("aerial", "drone"),
            ("pov", "pov"), ("first-person", "pov"),
            ("tracking", "tracking"), ("dolly", "tracking"),
            ("dutch", "dutch"), ("tilted", "dutch"),
            ("overhead", "overhead"), ("top-down", "overhead"), ("bird", "overhead"),
        ]:
            if keyword in raw_lower:
                return mapped
        return "medium"  # safe default
