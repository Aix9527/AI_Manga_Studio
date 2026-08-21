"""Phase 13.3: Episode Production Readiness Gate tests."""

from __future__ import annotations

import pytest

from backend.characters.bible_v2.service import CharacterBibleService
from backend.production.readiness import AssetReadinessGate
from backend.shot_dna.library import CATEGORIES, ShotDNALibrary
from backend.story.episode.repository import EpisodeRepository
from backend.story.episode.service import EpisodeService
from backend.world.service import WorldService


@pytest.fixture()
def gate(tmp_path):
    return AssetReadinessGate(
        CharacterBibleService(str(tmp_path / "bible")),
        WorldService(str(tmp_path / "world")),
        ShotDNALibrary(str(tmp_path / "dna.json")),
    )


@pytest.fixture()
def service_with_gate(tmp_path, gate):
    return EpisodeService(EpisodeRepository(str(tmp_path / "episodes.db")), readiness_gate=gate)


def _complete_bible(service: CharacterBibleService, cid: str) -> None:
    service.create(cid, name=f"角色{cid}")
    for key in ("front", "side", "back"):
        service.add_view(cid, key, prompt=f"{key} view")
    for key in ("neutral", "angry", "sad", "fear", "smile", "surprise"):
        service.add_expression(cid, key, prompt=f"{key} expr")
    for key in ("walk", "run", "fight", "sit", "interact", "emotional"):
        service.add_action(cid, key, description=key)


def test_gate_fails_when_no_assets(gate):
    report = gate.check_project("PROJ-EMPTY")
    assert report["ready"] is False
    # shot_dna ships a built-in seed library, so it is always ready
    assert set(report["missing"]) == {"character", "world"}
    assert report["gates"]["shot_dna"]["pass"] is True


def test_gate_partial_character_incomplete(tmp_path, gate):
    service = CharacterBibleService(str(tmp_path / "bible"))
    service.create("CH-A", name="陈夜")
    service.add_view("CH-A", "front", prompt="front")  # only one asset
    gate.characters = service
    report = gate.check_project("PROJ-PARTIAL")
    assert report["gates"]["character"]["pass"] is False
    assert "CH-A:ratio=" in report["gates"]["character"]["incomplete"][0]


def test_gate_passes_with_complete_assets(tmp_path, gate):
    bible_service = CharacterBibleService(str(tmp_path / "bible"))
    _complete_bible(bible_service, "CH-001")
    world = WorldService(str(tmp_path / "world"))
    world.create_world("PROJ-READY", name="归墟", era="未来科幻")
    world.note_environment("PROJ-READY", kind="physics_rule", content="禁止时间回溯")
    gate.characters = bible_service
    gate.world = world
    report = gate.check_project("PROJ-READY")
    assert report["ready"] is True
    assert report["missing"] == []
    assert report["gates"]["character"]["characters"] == 1


def test_gate_blocks_asset_ready_transition(service_with_gate, gate):
    episode = service_with_gate.create("PROJ-BLOCK", episode_no=1)
    for status in ["planning", "script_ready", "storyboard_ready"]:
        service_with_gate.transition(episode.id, status)
    with pytest.raises(ValueError, match="asset readiness gate blocked"):
        service_with_gate.transition(episode.id, "asset_ready")
    assert service_with_gate.get(episode.id).status == "storyboard_ready"


def test_gate_allows_asset_ready_when_ready(tmp_path):
    from backend.characters.bible_v2.service import CharacterBibleService
    bible_service = CharacterBibleService(str(tmp_path / "bible"))
    _complete_bible(bible_service, "CH-001")
    world = WorldService(str(tmp_path / "world"))
    world.create_world("PROJ-OK", name="归墟", era="未来科幻")
    world.note_environment("PROJ-OK", kind="physics_rule", content="禁止时间回溯")
    gate = AssetReadinessGate(bible_service, world, ShotDNALibrary(str(tmp_path / "dna.json")))
    service = EpisodeService(EpisodeRepository(str(tmp_path / "episodes.db")), readiness_gate=gate)
    episode = service.create("PROJ-OK", episode_no=1)
    for status in ["planning", "script_ready", "storyboard_ready", "asset_ready"]:
        episode = service.transition(episode.id, status)
    assert episode.status == "asset_ready"
