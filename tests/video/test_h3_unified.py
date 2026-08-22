from __future__ import annotations

import json

import pytest

from backend.video.h3_unified.reference_bundle import H3ReferenceBundle
from backend.video.h3_unified.ui_state import H3Mode, H3UnifiedRequest, build_ui_state


def test_reference_bundle_keeps_nine_semantic_slots_in_stable_order() -> None:
    bundle = H3ReferenceBundle(
        character_identity="character.png",
        location="location.png",
        prop="sword.png",
        storyboard="shot_grid.png",
        videos=("motion.mp4",),
        audios=("voice.wav",),
    )

    assert bundle.image_references() == [
        ("character_identity", "character.png"),
        ("location", "location.png"),
        ("prop", "sword.png"),
        ("storyboard", "shot_grid.png"),
    ]
    assert bundle.total_reference_files == 6


def test_reference_bundle_rejects_more_than_twelve_reference_files() -> None:
    with pytest.raises(ValueError, match="12"):
        H3ReferenceBundle(
            character_identity="1.png",
            secondary_character="2.png",
            location="3.png",
            costume="4.png",
            prop="5.png",
            expression="6.png",
            style="7.png",
            lighting="8.png",
            storyboard="9.png",
            videos=("1.mp4", "2.mp4", "3.mp4"),
            audios=("voice.wav",),
        )


def test_unified_state_matches_external_control_desk_contract_and_16gb_profile() -> None:
    request = H3UnifiedRequest(
        mode=H3Mode.REF2VA,
        prompt="苏晚在暴雨中的实验楼走廊快速回头，镜头跟拍。",
        references=H3ReferenceBundle(
            character_identity="suwan.png",
            location="lab.png",
            lighting="rain_light.png",
        ),
        aspect_ratio="9:16",
        resolution="480p",
        duration_seconds=5,
        steps=12,
        seed=20260822,
        gpu_vram_gb=16,
        shot_project="归墟觉醒·天倾",
        shot_episode=1,
        shot_scene=2,
        shot_number=3,
    )

    state = build_ui_state(request)

    assert state["schema"] == "ltoj-manga/control-desk-v1.0"
    assert state["director"]["mode"] == "Ref2VA"
    assert state["director"]["production"]["aspect_ratio"] == "9:16 竖屏"
    assert state["director"]["production"]["resolution"] == "480p"
    assert state["director"]["production"]["duration_seconds"] == 5
    assert state["runtime"]["profile"] == "balanced_offload_16gb"
    assert [slot["filename"] for slot in state["assets"]["images"] if slot["enabled"]] == [
        "suwan.png",
        "lab.png",
        "rain_light.png",
    ]
    json.dumps(state, ensure_ascii=False)


def test_unified_request_rejects_invalid_duration_and_step_count() -> None:
    with pytest.raises(ValueError, match="2.*15"):
        H3UnifiedRequest(mode=H3Mode.T2VA, prompt="test", duration_seconds=16)

    with pytest.raises(ValueError, match="steps"):
        H3UnifiedRequest(mode=H3Mode.T2VA, prompt="test", steps=9)
