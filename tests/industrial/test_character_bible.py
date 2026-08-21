"""Phase 13.1: Character Bible v2 tests (GPT spec)."""

from __future__ import annotations

import pytest

from backend.characters.bible_v2.service import CharacterBibleService
from backend.characters.bible_v2.model import ACTION_KEYS, EXPRESSION_KEYS, VIEW_KEYS


@pytest.fixture()
def service(tmp_path):
    return CharacterBibleService(str(tmp_path / "bible"))


def test_create_bible_identity(service):
    bible = service.create("CH001", name="陈夜", age=26, gender="male")
    assert bible.identity.name == "陈夜"
    assert bible.identity.age == 26
    assert bible.identity.source_character_id == "CH001"


def test_duplicate_bible_rejected(service):
    service.create("CH001")
    with pytest.raises(ValueError):
        service.create("CH001")


def test_version_management(service):
    service.create("CH001")
    service.add_version("CH001", "v1", appearance={"face": "sharp"}, clothing={"default": "夜行衣"})
    service.add_version("CH001", "v2", parent="v1", appearance={"face": "sharp", "scar": True})
    bible = service.set_version_status("CH001", "v2", approved=True, locked=True)
    assert "v1" in bible.versions and "v2" in bible.versions
    assert bible.versions["v2"].parent == "v1"
    assert bible.versions["v2"].approved is True
    assert bible.versions["v2"].locked is True


def test_three_views_expressions_actions(service):
    service.create("CH001")
    for key in VIEW_KEYS:
        service.add_view("CH001", key, image_path=f"views/{key}.png", prompt=f"{key} view")
    for key in EXPRESSION_KEYS:
        service.add_expression("CH001", key, image_path=f"expr/{key}.png")
    for key in ACTION_KEYS:
        service.add_action("CH001", key, description=f"{key} action")
    bible = service.get("CH001")
    assert set(bible.views.keys()) == set(VIEW_KEYS)
    assert set(bible.expressions.keys()) == set(EXPRESSION_KEYS)
    assert set(bible.actions.keys()) == set(ACTION_KEYS)
    completeness = bible.completeness()
    assert completeness["views"] == 3
    assert completeness["expressions"] == 6
    assert completeness["actions"] == 6
    assert completeness["ratio"] == 1.0


def test_invalid_asset_key_rejected(service):
    service.create("CH001")
    with pytest.raises(ValueError):
        service.add_expression("CH001", "angry_hulk")
    with pytest.raises(ValueError):
        service.add_view("CH001", "diagonal")


def test_update_identity(service):
    service.create("CH001", name="陈夜")
    bible = service.update_identity("CH001", background="废土幸存者", personality=["brave", "calm"])
    assert bible.identity.background == "废土幸存者"
    assert "brave" in bible.identity.personality


def test_missing_bible_raises(service):
    with pytest.raises(KeyError):
        service.completeness("NOPE")
