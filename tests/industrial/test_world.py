"""Phase 13.1: World Bible / Scene Bible / Location / Environment Memory tests."""

from __future__ import annotations

import pytest

from backend.world.service import WorldService


@pytest.fixture()
def service(tmp_path):
    return WorldService(str(tmp_path / "world"))


def test_world_bible_crud(service):
    world = service.create_world(
        "PROJ-1", name="归墟", era="未来都市", technology="AI文明",
        power_system="量子能力", visual_style="赛博朋克",
        physics_rules=["重力可编程", "禁止时间回溯"],
    )
    assert world.id.startswith("WLD-")
    got = service.get_world(world.id)
    assert got.era == "未来都市"
    assert got.power_system == "量子能力"
    assert "禁止时间回溯" in got.physics_rules

    updated = service.update_world(world.id, color_language="冷蓝+霓虹")
    assert updated.color_language == "冷蓝+霓虹"
    assert service.list_worlds("PROJ-1")[0].id == world.id


def test_scene_bible_crud(service):
    world = service.create_world("PROJ-1", name="归墟")
    scene = service.create_scene(
        "PROJ-1", world_id=world.id, name="地下城市入口",
        location="青云城地底", time="night", weather="rain",
        architecture="混凝土+发光纹路",
        camera_rules=["禁止手持抖动"], lighting_rules=["低照度冷色"],
        forbidden_elements=["现代汽车", "手机"],
    )
    got = service.get_scene(scene.id)
    assert got.weather == "rain"
    assert "现代汽车" in got.forbidden_elements
    assert len(service.list_scenes("PROJ-1")) == 1


def test_location_registry(service):
    world = service.create_world("PROJ-1", name="归墟")
    loc = service.create_location(
        "PROJ-1", world_id=world.id, name="青云城",
        geography="盆地", architecture="东方+废土",
        landmarks=["古遗迹", "中央塔"], connected_to=["地下城"],
    )
    got = service.get_location(loc.id)
    assert "古遗迹" in got.landmarks
    assert got.connected_to == ["地下城"]


def test_environment_memory(service):
    service.note_environment("PROJ-1", kind="physics_rule", content="禁止时间回溯")
    service.note_environment("PROJ-1", kind="forbidden_element", content="现代科技")
    summary = service.environment_summary("PROJ-1")
    assert summary["entries"] == 2
    assert summary["by_kind"]["physics_rule"] == 1
    assert summary["by_kind"]["forbidden_element"] == 1
    constraints = service.environment.constraints("PROJ-1")
    assert constraints[0]["content"] == "禁止时间回溯"
