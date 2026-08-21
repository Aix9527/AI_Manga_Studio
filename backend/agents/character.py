"""Character Agent — manages character context for image generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import uuid4


@dataclass
class CharacterContext:
    """Character context bundle for a generation request."""
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    character_id: str = ""
    shot_id: str = ""
    appearance_summary: str = ""
    current_costume: str = ""
    current_emotion: str = ""
    pose_hint: str = ""
    relationship_context: str = ""
    consistency_ref_image: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class CharacterAgent:
    """
    Character Agent — assembles character context for consistent generation.

    Responsibilities:
    - Retrieve character profiles from Character Memory
    - Assemble appearance + costume + emotion context per shot
    - Provide consistency reference images
    - Track character state changes across the pipeline
    """

    def __init__(self, memory_service=None):
        self.memory = memory_service  # CharacterService from Phase 1
        self.context_cache: dict[str, CharacterContext] = {}

    def set_memory(self, memory_service):
        self.memory = memory_service

    def get_context(
        self,
        character_id: str,
        shot_id: str,
        emotion: str = "",
        pose_hint: str = "",
    ) -> CharacterContext:
        """Assemble a character context bundle for a specific shot."""

        # Check cache first
        cache_key = f"{character_id}_{shot_id}"
        if cache_key in self.context_cache:
            return self.context_cache[cache_key]

        appearance = ""
        costume = ""
        ref_image = ""
        relationships = ""

        if self.memory:
            profile = self.memory.get_profile(character_id)
            if ch := profile.get("character"):
                appearance = self._format_appearance(ch)
                ref_image = self._get_ref_image(profile, character_id)
                relationships = self._format_relationships(profile)

        ctx = CharacterContext(
            character_id=character_id,
            shot_id=shot_id,
            appearance_summary=appearance,
            current_emotion=emotion,
            pose_hint=pose_hint,
            consistency_ref_image=ref_image,
            relationship_context=relationships,
        )

        self.context_cache[cache_key] = ctx
        return ctx

    def get_prompt_context(self, character_id: str, shot_id: str, emotion: str = "") -> str:
        """Generate a prompt-relevant character description."""
        ctx = self.get_context(character_id, shot_id, emotion)

        parts = [ctx.appearance_summary]
        if ctx.current_emotion:
            parts.append(f"Expression: {ctx.current_emotion}")
        if ctx.pose_hint:
            parts.append(f"Pose: {ctx.pose_hint}")
        if ctx.relationship_context:
            parts.append(f"Relationship context: {ctx.relationship_context}")

        return "; ".join(parts)

    def get_multi_character_context(self, character_ids: list[str], shot_id: str, emotions: dict = None) -> dict:
        """Get context for multiple characters in a single shot."""
        result = {}
        for cid in character_ids:
            emotion = emotions.get(cid, "") if emotions else ""
            ctx = self.get_context(cid, shot_id, emotion)
            result[cid] = ctx
        return result

    @staticmethod
    def _format_appearance(ch: dict) -> str:
        """Format character data into a compact appearance string."""
        parts = [
            f"{ch.get('name', 'Unknown')}",
            f"{ch.get('gender', '')}, age {ch.get('age', '?')}",
            f"species: {ch.get('species', 'human')}",
        ]
        appearance = ch.get("appearance", "")
        if isinstance(appearance, str) and appearance:
            parts.append(appearance)
        return " | ".join(parts)

    @staticmethod
    def _get_ref_image(profile: dict, character_id: str) -> str:
        """Get the primary reference image path."""
        images = profile.get("images", [])
        for img in images:
            if img.get("is_primary"):
                return img.get("file_path", "")
        return ""

    @staticmethod
    def _format_relationships(profile: dict) -> str:
        """Format relationships into context string."""
        rels = profile.get("relationships", [])
        if not rels:
            return ""
        parts = [f"{r.get('related_name', '?')} ({r.get('relation_type', 'unknown')})" for r in rels[:3]]
        return ", ".join(parts)
