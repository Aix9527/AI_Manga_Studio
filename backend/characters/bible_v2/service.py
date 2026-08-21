"""Character Bible v2 service (Phase 13.1)."""

from __future__ import annotations

from pathlib import Path

from backend.characters.bible_v2.model import (
    ACTION_KEYS,
    EXPRESSION_KEYS,
    VIEW_KEYS,
    BibleAction,
    BibleExpression,
    BibleIdentity,
    BibleVersion,
    BibleView,
    CharacterBible,
)
from backend.characters.bible_v2.repository import CharacterBibleRepository


class CharacterBibleService:
    def __init__(self, root: str | Path = "storage/characters/bible"):
        self.repo = CharacterBibleRepository(root)

    # ------------------------------------------------------------- create
    def create(self, character_id: str, name: str = "", age: int = 0, gender: str = "") -> CharacterBible:
        if self.repo.get(character_id):
            raise ValueError(f"bible already exists: {character_id}")
        identity = BibleIdentity(name=name, age=age, gender=gender, source_character_id=character_id)
        self.repo.save_identity(character_id, identity)
        bible = self.repo.get(character_id)
        assert bible is not None
        return bible

    def get(self, character_id: str) -> CharacterBible | None:
        return self.repo.get(character_id)

    def list(self) -> list[CharacterBible]:
        return self.repo.list()

    def update_identity(self, character_id: str, **fields) -> CharacterBible:
        bible = self.repo.get(character_id)
        if not bible:
            raise KeyError(f"bible not found: {character_id}")
        identity = bible.identity
        for key, value in fields.items():
            if value is not None and hasattr(identity, key):
                setattr(identity, key, value)
        self.repo.save_identity(character_id, identity)
        return self.repo.get(character_id)

    # ------------------------------------------------------------- versions
    def add_version(
        self,
        character_id: str,
        version_id: str,
        parent: str = "",
        appearance: dict | None = None,
        clothing: dict | None = None,
        notes: str = "",
        approved: bool = False,
    ) -> CharacterBible:
        bible = self.repo.get(character_id)
        if not bible:
            raise KeyError(f"bible not found: {character_id}")
        if version_id in bible.versions:
            raise ValueError(f"version already exists: {version_id}")
        version = BibleVersion(
            id=version_id, parent=parent, approved=approved, locked=False,
            appearance=appearance or {}, clothing=clothing or {}, notes=notes,
        )
        self.repo.save_version(character_id, version)
        return self.repo.get(character_id)

    def set_version_status(self, character_id: str, version_id: str, *, approved: bool | None = None, locked: bool | None = None) -> CharacterBible:
        bible = self.repo.get(character_id)
        if not bible or version_id not in bible.versions:
            raise KeyError(f"version not found: {character_id}/{version_id}")
        version = bible.versions[version_id]
        if approved is not None:
            version.approved = approved
        if locked is not None:
            version.locked = locked
        self.repo.save_version(character_id, version)
        return self.repo.get(character_id)

    # ------------------------------------------------------------- assets
    def add_view(self, character_id: str, key: str, image_path: str = "", prompt: str = "", seed: int = 0) -> CharacterBible:
        if key not in VIEW_KEYS:
            raise ValueError(f"invalid view key: {key} (allowed: {VIEW_KEYS})")
        self.repo.save_view(character_id, BibleView(key=key, image_path=image_path, prompt=prompt, seed=seed))
        return self.repo.get(character_id)

    def add_expression(self, character_id: str, key: str, image_path: str = "", prompt: str = "", seed: int = 0) -> CharacterBible:
        if key not in EXPRESSION_KEYS:
            raise ValueError(f"invalid expression key: {key} (allowed: {EXPRESSION_KEYS})")
        self.repo.save_expression(character_id, BibleExpression(key=key, image_path=image_path, prompt=prompt, seed=seed))
        return self.repo.get(character_id)

    def add_action(self, character_id: str, key: str, description: str = "", prompt: str = "", image_path: str = "") -> CharacterBible:
        if key not in ACTION_KEYS:
            raise ValueError(f"invalid action key: {key} (allowed: {ACTION_KEYS})")
        self.repo.save_action(character_id, BibleAction(key=key, description=description, prompt=prompt, image_path=image_path))
        return self.repo.get(character_id)

    # ------------------------------------------------------------- queries
    def completeness(self, character_id: str) -> dict:
        bible = self.repo.get(character_id)
        if not bible:
            raise KeyError(f"bible not found: {character_id}")
        return bible.completeness()

    def export_json(self, character_id: str, target: str | Path) -> Path:
        return self.repo.export_json(character_id, target)
