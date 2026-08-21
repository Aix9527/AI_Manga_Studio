"""Character service layer — business logic orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from backend.characters.memory import CharacterMemory
from backend.characters.extractor import CharacterExtractor
from backend.characters.consistency import ConsistencyChecker
from backend.characters.models import (
    Character, CharacterTrait, CharacterImage, CharacterCostume,
    CharacterRelationship, CharacterEmbedding,
)


class CharacterService:
    """High-level API for character management."""

    def __init__(
        self,
        db_path: str = "storage/orchestrator.db",
        media_roots: Optional[Iterable[str | Path]] = None,
    ):
        self.memory = CharacterMemory(db_path)
        self.extractor = CharacterExtractor()
        self.consistency = ConsistencyChecker(db_path)
        roots = media_roots if media_roots is not None else ("storage", "projects")
        self.media_roots = tuple(Path(root).resolve() for root in roots)

    # ── Extract & Import ──

    def extract_from_text(self, text: str, novel_id: str = "") -> list[Character]:
        """Extract characters from novel text and persist them."""
        chars = self.extractor.extract_from_text(text, novel_id=novel_id)
        for ch in chars:
            self.memory.create(ch)
        return chars

    def import_character(self, data: dict) -> Character:
        """Import a character from a dictionary (API/json)."""
        from backend.characters.models import (
            Appearance, FaceAppearance, BodyAppearance, HairAppearance,
            Personality, CombatStyle,
        )

        appearance_data = data.get("appearance", {})
        appearance = Appearance(
            face=FaceAppearance(**appearance_data.get("face", {})),
            body=BodyAppearance(**appearance_data.get("body", {})),
            hair=HairAppearance(**appearance_data.get("hair", {})),
            eyes=appearance_data.get("eyes", ""),
            age_apparent=appearance_data.get("age_apparent", 0),
        )

        personality_data = data.get("personality", {})
        personality = Personality(**{k: v for k, v in personality_data.items() if k in Personality.__dataclass_fields__})

        combat_data = data.get("combat_style", {})
        combat_style = CombatStyle(**{k: v for k, v in combat_data.items() if k in CombatStyle.__dataclass_fields__})

        ch = Character(
            name=data.get("name", ""),
            aliases=data.get("aliases", []),
            species=data.get("species", "human"),
            gender=data.get("gender", ""),
            age=data.get("age", 0),
            role=data.get("role", ""),
            archetype=data.get("archetype", ""),
            appearance=appearance,
            personality=personality,
            combat_style=combat_style,
            backstory=data.get("backstory", ""),
            goal=data.get("goal", ""),
            arc_description=data.get("arc_description", ""),
            novel_id=data.get("novel_id", ""),
        )
        self.memory.create(ch)
        return ch

    # ── Query ──

    def get_profile(self, character_id: str) -> dict:
        return self.memory.export_profile(character_id)

    def search(self, keyword: str) -> list[dict]:
        return self.memory.search(keyword)

    def list_all(self, novel_id: str = "") -> list[dict]:
        return self.memory.list(novel_id)

    # ── Image Management ──

    def add_image(self, character_id: str, image_path: str, image_type: str = "reference", is_primary: bool = False, prompt: str = "") -> CharacterImage:
        img = CharacterImage(
            character_id=character_id,
            image_type=image_type,
            file_path=image_path,
            prompt_used=prompt,
            is_primary=is_primary,
        )
        self.memory.add_image(img)

        # Register reference embedding for consistency
        if is_primary:
            self.consistency.register_reference(character_id, image_path)

        return img

    def check_consistency(self, character_id: str, generated_image_path: str) -> dict:
        return self.consistency.check_consistency(character_id, generated_image_path)

    def resolve_image_path(self, image_id: str) -> Path:
        """Resolve a recorded image without allowing caller-controlled traversal."""
        image = self.memory.get_image(image_id)
        if not image:
            raise KeyError(image_id)

        recorded = Path(image["file_path"])
        candidates = (
            [recorded.resolve()]
            if recorded.is_absolute()
            else [(root / recorded).resolve() for root in self.media_roots]
        )
        safe_candidates = [
            candidate
            for candidate in candidates
            if any(candidate.is_relative_to(root) for root in self.media_roots)
        ]
        if not safe_candidates:
            raise PermissionError(image_id)

        allowed_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
        candidate = next((path for path in safe_candidates if path.is_file()), safe_candidates[0])
        if candidate.suffix.lower() not in allowed_suffixes:
            raise ValueError(candidate.suffix)
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        return candidate

    # ── Relationship ──

    def add_relationship(self, character_id: str, related_id: str, relation_type: str, description: str = "") -> CharacterRelationship:
        rel = CharacterRelationship(
            character_id=character_id,
            related_id=related_id,
            relation_type=relation_type,
            description=description,
        )
        self.memory.add_relationship(rel)
        return rel

    # ── Delete ──

    def delete(self, character_id: str) -> bool:
        return self.memory.delete(character_id)
