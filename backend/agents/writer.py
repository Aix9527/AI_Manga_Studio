"""Writer Agent — generates scene descriptions, dialogue polish, narrative flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import uuid4


@dataclass
class WriterResult:
    """Writer's output for a scene or shot."""
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    target_id: str = ""        # scene_id or shot_id
    target_type: str = ""      # scene or shot
    enhanced_description: str = ""
    polished_dialogue: str = ""
    narrative_notes: str = ""
    word_count_delta: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class WriterAgent:
    """
    Writer Agent — enhances narrative quality for manga adaptation.

    Responsibilities:
    - Polish scene descriptions for visual clarity
    - Enhance dialogue for impact
    - Add narrative notes (pacing, tension, emotional arc)
    - Ensure scene transitions are coherent
    """

    def enhance_scene(self, scene_data: dict) -> WriterResult:
        """Enhance a scene description for visual storytelling."""
        raw_text = scene_data.get("raw_text", "")
        scene_id = scene_data.get("id", "")

        # Extract key visual elements
        enhanced = self._enhance_for_visual(raw_text)
        dialogue = self._polish_dialogue(raw_text)
        notes = self._generate_notes(raw_text)

        return WriterResult(
            target_id=scene_id,
            target_type="scene",
            enhanced_description=enhanced,
            polished_dialogue=dialogue,
            narrative_notes=notes,
            word_count_delta=len(enhanced) - len(raw_text),
        )

    def enhance_shot(self, shot_data: dict) -> WriterResult:
        """Enhance a single shot description for panel generation."""
        description = shot_data.get("description", "")
        shot_id = shot_data.get("id", "")

        enhanced = self._enhance_for_visual(description)
        notes = self._generate_shot_notes(shot_data)

        return WriterResult(
            target_id=shot_id,
            target_type="shot",
            enhanced_description=enhanced,
            narrative_notes=notes,
            word_count_delta=len(enhanced) - len(description),
        )

    @staticmethod
    def _enhance_for_visual(text: str) -> str:
        """
        Rewrite prose into visual-director language.

        Converts: "He walked into the room, feeling nervous."
        To:      "[Shot: MC enters, medium shot. Sweat on brow. Hands trembling.
                  Warm light from window casts long shadow behind.]"

        This is heuristic — in production, pipe through an LLM.
        """
        lines: list[str] = []

        for line in text.strip().split("."):
            line = line.strip()
            if not line:
                continue

            # Tag emotional cues
            if any(kw in line.lower() for kw in ["feel", "felt", "thought", "knew"]):
                lines.append(f"[{line}] ← internal state — visualize through action/expression")
            elif any(kw in line.lower() for kw in ["said", "asked", "replied", "shouted", "whispered"]):
                lines.append(f"[DIALOGUE: {line}]")
            else:
                lines.append(f"[{line}]")

        return "\n".join(lines)

    @staticmethod
    def _polish_dialogue(text: str) -> str:
        """Extract and organize dialogue lines."""
        dialogue_lines = []
        for line in text.split("\n"):
            if "said" in line.lower() or '"' in line or '"' in line or '「' in line:
                dialogue_lines.append(line.strip())
        return "\n".join(dialogue_lines) if dialogue_lines else ""

    @staticmethod
    def _generate_notes(text: str) -> str:
        """Generate narrative pacing notes."""
        notes: list[str] = []

        word_count = len(text.split())
        if word_count < 50:
            notes.append("SHORT: consider splitting into more panels for pacing")
        elif word_count > 200:
            notes.append("LONG: may need to split into multiple shots")

        # Emotion detection
        text_lower = text.lower()
        emotion_kws = {
            "action": ["attack", "fight", "run", "jump", "strike", "dodge"],
            "emotional": ["cry", "tear", "scream", "laugh", "hug", "kiss"],
            "suspense": ["shadow", "silence", "creep", "whisper", "hidden"],
        }
        dominant = max(emotion_kws, key=lambda k: sum(kw in text_lower for kw in emotion_kws[k]))
        notes.append(f"TONE: {dominant}")

        return "\n".join(notes)

    @staticmethod
    def _generate_shot_notes(shot_data: dict) -> str:
        notes: list[str] = []
        shot_type = shot_data.get("shot_type", "")
        emotion = shot_data.get("emotion", "")

        if shot_type == "close-up":
            notes.append("Ensure character expression clearly conveys the emotion")
        if shot_type == "wide":
            notes.append("Establish environment details in background")
        if emotion in ("tense", "dramatic"):
            notes.append("Use dynamic angles and strong contrast")

        return "\n".join(notes) if notes else "Standard panel"
