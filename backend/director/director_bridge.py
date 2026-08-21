"""Director v2 bridge — Story Section Memory -> Director v2 -> ShotDirective JSON.

Phase 10.2-A: connects the new Director v2 and story memory into the existing
pipeline so shot directives (camera/lighting/emotion/continuity) are available
to the Prompt Compiler and ComfyUI generation stages.
"""

from __future__ import annotations

from dataclasses import asdict

from backend.story.parser import StoryParser
from backend.story.section_memory import StorySectionMemory
from backend.agents.director_v2 import ShotDirective
from backend.director.hybrid import HybridDirector
from backend.director.providers import default_llm_provider


class DirectorBridge:
    """Parses text -> sections -> shot directives in one call."""

    def __init__(
        self,
        parser: StoryParser | None = None,
        section_memory: StorySectionMemory | None = None,
        director=None,
        llm_provider="auto",
    ):
        """Phase 10.7-B: the default director is the HybridDirector router.

        ``llm_provider`` semantics:
        - "auto" (default): auto-detect a configured LLM (Qwen / OpenAI /
          Claude); falls back to rule-v2 when none is configured.
        - None: force the rule provider only (deterministic, offline).
        - a provider instance: use it as the LLM director.
        rule-v2 stays the permanent fallback.
        """
        self.parser = parser or StoryParser()
        self.section_memory = section_memory or StorySectionMemory()
        if director is not None:
            self.director = director
        elif llm_provider is None:
            self.director = HybridDirector(llm_provider=None)
        else:
            detected = None if llm_provider == "auto" else llm_provider
            self.director = HybridDirector(llm_provider=detected or default_llm_provider())

    def plan_hierarchy(self, hierarchy, novel_id: str = "", *, persist: bool = False) -> dict:
        """Plan a chapter->scene->shot hierarchy into directives + section memory."""
        sections = []
        prev_section = None
        all_shots = []
        for chapter, scene_data in hierarchy:
            for scene, shots in scene_data:
                section = self.section_memory.build_section(scene, chapter, prev_section)
                if persist and novel_id:
                    self.section_memory.save(novel_id, section)
                sections.append(section)
                prev_section = section
                all_shots.extend(shots)

        directives = self.director.plan_sequence(all_shots, sections)
        return {
            "novel_id": novel_id,
            "chapters": len(hierarchy),
            "scenes": len(sections),
            "shots_total": len(all_shots),
            "sections": [
                {
                    "section_key": s.section_key,
                    "scene_id": s.scene_id,
                    "emotion": s.emotion,
                    "visual_theme": s.visual_theme,
                    "character_state": s.character_state,
                    "previous_event": s.previous_event,
                }
                for s in sections
            ],
            "directives": [asdict(d) for d in directives],
        }

    def plan_text(self, text: str, novel_id: str = "", *, persist: bool = False) -> dict:
        """Acceptance entry point: novel snippet -> directives JSON (GPT spec)."""
        hierarchy = self.parser.parse_hierarchy(text, novel_id)
        return self.plan_hierarchy(hierarchy, novel_id=novel_id, persist=persist)

    @staticmethod
    def directives_json(directives: list[ShotDirective]) -> list[dict]:
        return [asdict(d) for d in directives]
