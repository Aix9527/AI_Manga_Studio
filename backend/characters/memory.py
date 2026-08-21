"""Character Memory — persistent identity across sessions."""

from __future__ import annotations

from typing import Optional

from backend.characters.models import (
    Character, CharacterTrait, CharacterImage, CharacterCostume,
    CharacterRelationship, CharacterEmbedding, Appearance,
)
from backend.characters.repository import CharacterRepository


class CharacterMemory:
    """
    Long-term character memory system.
    Stores full character identity profiles and retrieves them by ID or name.
    """

    def __init__(self, db_path: str = "storage/orchestrator.db"):
        self.repo = CharacterRepository(db_path)
        self.repo.initialize_schema()

    # ── Character CRUD ──

    def create(self, character: Character) -> Character:
        return self.repo.save_character(character)

    def get(self, character_id: str) -> Optional[dict]:
        return self.repo.get_character(character_id)

    def find_by_name(self, name: str, novel_id: str = "") -> list[dict]:
        all_chars = self.repo.list_characters(novel_id=novel_id)
        return [c for c in all_chars if c["name"].lower() == name.lower()]

    def list(self, novel_id: str = "") -> list[dict]:
        return self.repo.list_characters(novel_id=novel_id)

    def search(self, keyword: str) -> list[dict]:
        return self.repo.search_characters(keyword)

    def delete(self, character_id: str) -> bool:
        return self.repo.delete_character(character_id)

    # ── Traits ──

    def add_trait(self, trait: CharacterTrait) -> CharacterTrait:
        return self.repo.save_trait(trait)

    def get_traits(self, character_id: str) -> list[dict]:
        return self.repo.list_traits(character_id)

    # ── Images ──

    def add_image(self, image: CharacterImage) -> CharacterImage:
        return self.repo.save_image(image)

    def get_images(self, character_id: str) -> list[dict]:
        return self.repo.list_images(character_id)

    def get_image(self, image_id: str) -> Optional[dict]:
        return self.repo.get_image(image_id)

    def get_primary_image(self, character_id: str) -> Optional[dict]:
        return self.repo.get_primary_image(character_id)

    # ── Costumes ──

    def add_costume(self, costume: CharacterCostume) -> CharacterCostume:
        return self.repo.save_costume(costume)

    def get_costumes(self, character_id: str) -> list[dict]:
        return self.repo.list_costumes(character_id)

    # ── Relationships ──

    def add_relationship(self, rel: CharacterRelationship) -> CharacterRelationship:
        return self.repo.save_relationship(rel)

    def get_relationships(self, character_id: str) -> list[dict]:
        return self.repo.list_relationships(character_id)

    def get_relationship_graph(self, character_id: str, depth: int = 2) -> dict:
        return self.repo.get_relationship_graph(character_id, depth)

    # ── Embeddings ──

    def add_embedding(self, emb: CharacterEmbedding) -> CharacterEmbedding:
        return self.repo.save_embedding(emb)

    def get_embedding(self, character_id: str, embedding_type: str = "visual") -> Optional[dict]:
        return self.repo.get_embedding(character_id, embedding_type)

    # ── Profile Export ──

    def export_profile(self, character_id: str) -> dict:
        """Export a full character profile with all sub-records."""
        ch = self.get(character_id)
        if not ch:
            return {}
        return {
            "character": ch,
            "traits": self.get_traits(character_id),
            "images": self.get_images(character_id),
            "costumes": self.get_costumes(character_id),
            "relationships": self.get_relationships(character_id),
        }
