from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ReferenceRegistry:
    characters: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_character_designs(cls, characters: list[dict[str, Any]]) -> "ReferenceRegistry":
        registry = cls()
        for char in characters:
            name = str(char.get("name", "")).strip()
            if not name:
                continue
            assets: dict[str, dict[str, str]] = {}
            reference = str(char.get("reference_image", "")).strip()
            if reference:
                assets["front"] = {"path": reference, "role": "primary"}
            full_body = str(char.get("full_body_image", "")).strip()
            if full_body:
                assets["full_body"] = {"path": full_body, "role": "body_reference"}
            if assets:
                registry.characters[name] = {"name": name, "assets": assets}
        return registry

    @classmethod
    def load(cls, path: str | Path) -> "ReferenceRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if "characters" in payload and isinstance(payload["characters"], dict):
            return cls(characters=payload["characters"])
        return cls.from_legacy_map(payload)

    @classmethod
    def from_legacy_map(cls, payload: dict[str, Any]) -> "ReferenceRegistry":
        return cls.from_character_designs(
            [{"name": name, "reference_image": path} for name, path in payload.items()]
        )

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"characters": self.characters}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target

    def resolve_primary_reference(self, character_name: str) -> str:
        entry = self.characters.get(character_name) or {}
        assets = entry.get("assets", {})
        for key in ("front", "primary", "three_quarter", "full_body"):
            asset = assets.get(key)
            if isinstance(asset, dict) and asset.get("path"):
                return str(asset["path"])
        for asset in assets.values():
            if isinstance(asset, dict) and asset.get("path"):
                return str(asset["path"])
        return ""
