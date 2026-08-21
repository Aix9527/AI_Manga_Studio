import json
from pathlib import Path

from backend.production.reference_registry import ReferenceRegistry


def test_reference_registry_round_trips_primary_character_assets(tmp_path: Path):
    registry = ReferenceRegistry.from_character_designs(
        [
            {
                "name": "林舟",
                "reference_image": str(tmp_path / "lin_front.png"),
                "full_body_image": str(tmp_path / "lin_full.png"),
            }
        ]
    )
    path = registry.save(tmp_path / "reference_registry.json")

    loaded = ReferenceRegistry.load(path)

    assert loaded.resolve_primary_reference("林舟") == str(tmp_path / "lin_front.png")
    assert loaded.characters["林舟"]["assets"]["front"]["path"] == str(tmp_path / "lin_front.png")
    assert loaded.characters["林舟"]["assets"]["full_body"]["path"] == str(tmp_path / "lin_full.png")


def test_reference_registry_loads_legacy_character_refs_map(tmp_path: Path):
    legacy = tmp_path / "character_refs.json"
    legacy.write_text(json.dumps({"阿宁": "refs/aning.png"}, ensure_ascii=False), encoding="utf-8")

    loaded = ReferenceRegistry.load(legacy)

    assert loaded.resolve_primary_reference("阿宁") == "refs/aning.png"
