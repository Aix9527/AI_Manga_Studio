"""Character Bible v2 repository — folder/YAML persistence (Phase 13.1)."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import yaml

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

_BIBLE_ROOT = "storage/characters/bible"


def _dump(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class CharacterBibleRepository:
    def __init__(self, root: str | Path = _BIBLE_ROOT):
        self.root = Path(root)

    def character_dir(self, character_id: str) -> Path:
        return self.root / character_id

    # ------------------------------------------------------------- read
    def get(self, character_id: str) -> CharacterBible | None:
        base = self.character_dir(character_id)
        if not (base / "identity.yaml").exists():
            return None
        identity = BibleIdentity(**_load_yaml(base / "identity.yaml"))
        versions = {}
        for path in sorted((base / "versions").glob("*.yaml")):
            data = _load_yaml(path)
            version = BibleVersion(**{k: v for k, v in data.items() if k in BibleVersion.__dataclass_fields__})
            versions[version.id] = version
        def _without_key(path: Path) -> dict:
            return {k: v for k, v in _load_yaml(path).items() if k != "key"}

        views = {
            key: BibleView(key=key, **_without_key(base / "views" / key))
            for key in VIEW_KEYS if (base / "views" / key).exists()
        }
        expressions = {
            key: BibleExpression(key=key, **_without_key(base / "expressions" / key))
            for key in EXPRESSION_KEYS if (base / "expressions" / key).exists()
        }
        actions = {
            key: BibleAction(key=key, **_without_key(base / "actions" / key))
            for key in ACTION_KEYS if (base / "actions" / key).exists()
        }
        return CharacterBible(
            character_id=character_id,
            identity=identity,
            versions=versions,
            views=views,
            expressions=expressions,
            actions=actions,
            updated_at=str((base / "identity.yaml").stat().st_mtime),
        )

    def list(self) -> list[CharacterBible]:
        if not self.root.exists():
            return []
        return [b for cid in sorted(p.name for p in self.root.iterdir() if p.is_dir()) if (b := self.get(cid))]

    # ------------------------------------------------------------- write
    def save_identity(self, character_id: str, identity: BibleIdentity) -> None:
        _dump(self.character_dir(character_id) / "identity.yaml", asdict(identity))

    def save_version(self, character_id: str, version: BibleVersion) -> None:
        _dump(self.character_dir(character_id) / "versions" / f"{version.id}.yaml", asdict(version))

    def save_view(self, character_id: str, view: BibleView) -> None:
        _dump(self.character_dir(character_id) / "views" / view.key, asdict(view))

    def save_expression(self, character_id: str, expression: BibleExpression) -> None:
        _dump(self.character_dir(character_id) / "expressions" / expression.key, asdict(expression))

    def save_action(self, character_id: str, action: BibleAction) -> None:
        _dump(self.character_dir(character_id) / "actions" / action.key, asdict(action))

    def export_json(self, character_id: str, target: str | Path) -> Path:
        bible = self.get(character_id)
        if not bible:
            raise KeyError(f"bible not found: {character_id}")
        target = Path(target)
        _write_json(target, bible.to_dict())
        return target
