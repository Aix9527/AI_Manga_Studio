"""Deterministic, source-grounded chapter planning for novel-video runs.

This module deliberately does not call a cloud model.  It turns selected real
chapter excerpts into immutable planning contracts; later stages may enrich the
prompts, but cannot substitute a fixed demonstration story for source text.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import re
from typing import Literal

from backend.production.contracts import (
    Chapter,
    ChapterPlanBundle,
    DialogueLine,
    LoadedInput,
    ScenePlan,
    ShotPlan,
)


_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?……])\s*|\n+")
_CLAUSE_BOUNDARY = re.compile(r"(?<=[，；：])")
_DIALOGUE = re.compile(r"[“\"]([^”\"]{2,80})[”\"]")
_TIME_JUMP_MARKERS = ("次日", "翌日", "多年后", "数日后", "第二天", "清晨", "深夜")
_LOCATION_JUMP_MARKERS = ("来到", "抵达", "离开", "另一边", "城外", "门外")
_NEGATIVE_PROMPT = (
    "deformed anatomy, malformed hands, duplicate person, low resolution, blur, "
    "text, logo, subtitle, watermark"
)


class ChapterPlanner:
    """Build a versioned plan from user-selected chapters only."""

    plan_version = "chapter-plan-v1"

    def plan(
        self,
        loaded: LoadedInput,
        *,
        chapter_indexes: list[int] | tuple[int, ...],
        target_seconds: float = 60,
        max_shots: int | None = None,
    ) -> ChapterPlanBundle:
        if target_seconds < 5:
            raise ValueError("H3 target_seconds must be at least 5 seconds")
        selected = self._select_chapters(loaded, chapter_indexes)
        source_text = "\n".join(chapter.content for chapter in selected)
        candidates = self._story_candidates(selected)
        if not candidates:
            raise ValueError("selected chapter has no usable story text")

        suggested = self.suggested_shot_count(target_seconds)
        requested = suggested if max_shots is None else max_shots
        if requested < 1:
            raise ValueError("max_shots must be at least one")
        # H3 needs at least five seconds per segment.  The user-supplied shot
        # cap wins, and a short duration therefore lowers the achievable count.
        shot_count = min(requested, len(candidates), int(target_seconds // 5))
        chosen = self._select_candidates(candidates, shot_count)
        purposes = self._purposes_for(shot_count)
        duration = min(15.0, max(5.0, target_seconds / shot_count))

        shots: list[ShotPlan] = []
        scenes: list[ScenePlan] = []
        seen_chapter_indexes: set[int] = set()
        for sequence, ((chapter, excerpt), purpose) in enumerate(
            zip(chosen, purposes), start=1
        ):
            first_for_chapter = chapter.index not in seen_chapter_indexes
            continuity, inherit_tail = self._continuity(
                first_for_chapter, excerpt
            )
            seen_chapter_indexes.add(chapter.index)
            scene_id = f"chapter-{chapter.index:03d}-scene-{sequence:02d}"
            shot = ShotPlan(
                id=f"{scene_id}-shot-01",
                sequence=sequence,
                scene_id=scene_id,
                source_excerpt=excerpt,
                narrative_purpose=purpose,
                duration_seconds=duration,
                continuity=continuity,
                inherit_tail=inherit_tail,
                prompt=self._prompt(excerpt, purpose, continuity),
                negative_prompt=_NEGATIVE_PROMPT,
                dialogue=self._dialogue(excerpt),
                narration=excerpt,
                ambience_prompt=self._ambience(excerpt, purpose),
            )
            shots.append(shot)
            scenes.append(
                ScenePlan(
                    id=scene_id,
                    chapter_index=chapter.index,
                    source_excerpt=excerpt,
                    narrative_purpose=purpose,
                    shots=(shot,),
                )
            )

        # Floating division can introduce a sub-microsecond overrun.  Keep the
        # stored duration within the contract budget deterministically.
        if sum(shot.duration_seconds for shot in shots) > target_seconds:
            final = shots[-1]
            prior = sum(shot.duration_seconds for shot in shots[:-1])
            corrected = max(5.0, target_seconds - prior)
            shots[-1] = replace(final, duration_seconds=corrected)
            scenes[-1] = replace(scenes[-1], shots=(shots[-1],))

        return ChapterPlanBundle(
            plan_version=self.plan_version,
            source_sha256=str(
                loaded.contract.metadata.get("sha256")
                or sha256(source_text.encode("utf-8")).hexdigest()
            ),
            chapter_indexes=tuple(chapter.index for chapter in selected),
            target_seconds=target_seconds,
            suggested_shot_count=suggested,
            scenes=tuple(scenes),
            shots=tuple(shots),
        )

    @staticmethod
    def suggested_shot_count(target_seconds: float) -> int:
        """Return the 60-second recommendation (8-12) scaled for other budgets."""
        if target_seconds < 5:
            raise ValueError("H3 target_seconds must be at least 5 seconds")
        if target_seconds >= 48:
            return min(12, max(8, round(target_seconds / 6)))
        return max(1, min(12, round(target_seconds / 6)))

    @staticmethod
    def _select_chapters(
        loaded: LoadedInput, indexes: list[int] | tuple[int, ...]
    ) -> list[Chapter]:
        if not indexes:
            raise ValueError("at least one chapter index is required")
        wanted = list(dict.fromkeys(indexes))
        by_index = {chapter.index: chapter for chapter in loaded.chapters}
        missing = [index for index in wanted if index not in by_index]
        if missing:
            raise ValueError(f"unknown chapter indexes: {missing}")
        return [by_index[index] for index in wanted]

    @staticmethod
    def _story_excerpts(text: str) -> list[str]:
        sentences = [part.strip() for part in _SENTENCE_BOUNDARY.split(text) if part.strip()]
        excerpts: list[str] = []
        for sentence in sentences:
            if len(sentence) <= 90:
                excerpts.append(sentence)
                continue
            excerpts.extend(
                clause.strip() for clause in _CLAUSE_BOUNDARY.split(sentence)
                if len(clause.strip()) >= 8
            )
        return excerpts or ([text.strip()] if text.strip() else [])

    @staticmethod
    def _story_candidates(chapters: list[Chapter]) -> list[tuple[Chapter, str]]:
        """Preserve chapter identity even when two chapters quote the same text."""
        return [
            (chapter, excerpt)
            for chapter in chapters
            for excerpt in ChapterPlanner._story_excerpts(chapter.content)
        ]

    @staticmethod
    def _evenly_select_indexes(length: int, count: int) -> list[int]:
        if count == 1:
            return [0]
        return [
            round(index * (length - 1) / (count - 1))
            for index in range(count)
        ]

    @classmethod
    def _select_candidates(
        cls, candidates: list[tuple[Chapter, str]], count: int
    ) -> list[tuple[Chapter, str]]:
        """Select in source order, reserving each selected chapter's first beat.

        If a caller caps shots below the chapter count, that explicit limit wins
        and the earliest chapters are selected.  Otherwise each selected chapter
        receives a first shot, which must never inherit another chapter's tail.
        """
        first_indexes: list[int] = []
        seen_chapters: set[int] = set()
        for index, (chapter, _) in enumerate(candidates):
            if chapter.index not in seen_chapters:
                first_indexes.append(index)
                seen_chapters.add(chapter.index)
        if count < len(first_indexes):
            return candidates[:count]

        selected_indexes = set(first_indexes)
        remaining = count - len(selected_indexes)
        if remaining:
            available = [
                index for index in range(len(candidates)) if index not in selected_indexes
            ]
            for local_index in cls._evenly_select_indexes(len(available), remaining):
                selected_indexes.add(available[local_index])
        return [candidates[index] for index in sorted(selected_indexes)]

    @staticmethod
    def _purposes_for(count: int) -> list[str]:
        if count == 1:
            return ["opening_cliffhanger"]
        if count == 2:
            return ["opening", "cliffhanger"]
        if count == 3:
            return ["opening", "conflict", "cliffhanger"]
        purposes = ["opening"]
        middle = count - 2
        for index in range(middle):
            purposes.append("conflict" if index < middle - 1 else "turn")
        return purposes + ["cliffhanger"]

    @staticmethod
    def _continuity(
        first_for_chapter: bool, excerpt: str
    ) -> tuple[Literal["same_action", "same_character_new_scene", "time_jump", "location_jump"], bool]:
        if first_for_chapter:
            return "location_jump", False
        if any(marker in excerpt for marker in _TIME_JUMP_MARKERS):
            return "time_jump", False
        if any(marker in excerpt for marker in _LOCATION_JUMP_MARKERS):
            return "location_jump", False
        return "same_action", True

    @staticmethod
    def _prompt(excerpt: str, purpose: str, continuity: str) -> str:
        prefix = (
            "Continue from <Picture 1>, preserving character, pose, environment, "
            "lighting, and camera position; advance the action without replaying it. "
            if continuity == "same_action"
            else "Establish the new story state with source-faithful details. "
        )
        return f"{prefix}Cinematic {purpose} beat: {excerpt}"

    @staticmethod
    def _dialogue(excerpt: str) -> tuple[DialogueLine, ...]:
        return tuple(DialogueLine(speaker="unknown", text=line) for line in _DIALOGUE.findall(excerpt))

    @staticmethod
    def _ambience(excerpt: str, purpose: str) -> str:
        lowered = excerpt.lower()
        if "雨" in excerpt or "storm" in lowered:
            return "steady rain, distant thunder, wet surface reflections"
        if purpose in {"conflict", "turn"}:
            return "tense room tone, restrained impact sounds, rising wind"
        if purpose == "cliffhanger":
            return "unresolved wind, distant echo, abrupt silence"
        return "natural location ambience, restrained cinematic atmosphere"


def plan(
    loaded: LoadedInput,
    *,
    chapter_indexes: list[int] | tuple[int, ...],
    target_seconds: float = 60,
    max_shots: int | None = None,
) -> ChapterPlanBundle:
    """Convenience entry point for the formal service layer."""
    return ChapterPlanner().plan(
        loaded,
        chapter_indexes=chapter_indexes,
        target_seconds=target_seconds,
        max_shots=max_shots,
    )
