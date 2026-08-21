import json

import pytest

from backend.production.h3_unified.contracts import (
    H3AudioRole,
    H3ImageRole,
    H3Mode,
    H3ReferenceBundle,
    H3ReferenceItem,
    H3UnifiedOptions,
    H3VideoRole,
)
from backend.production.h3_unified.control_state import (
    CONTROL_DESK_NODE,
    build_control_desk_state,
    build_control_desk_workflow,
)


def test_control_desk_state_maps_semantic_slots_and_uses_uploaded_relative_names():
    bundle = H3ReferenceBundle(
        images=(
            H3ReferenceItem("image", H3ImageRole.CHARACTER_IDENTITY, r"D:\refs\hero.png"),
            H3ReferenceItem("image", H3ImageRole.LOCATION, r"D:\refs\lab.png"),
        ),
        videos=(
            H3ReferenceItem(
                "video", H3VideoRole.ACTION_RHYTHM, r"D:\refs\motion.mp4",
                include_audio=True, duration_seconds=4.5,
            ),
        ),
        audios=(
            H3ReferenceItem(
                "audio", H3AudioRole.PROTAGONIST_VOICE, r"D:\refs\voice.wav",
                duration_seconds=3.0,
            ),
        ),
    )
    options = H3UnifiedOptions(
        mode=H3Mode.REF2VA,
        runtime="control_desk",
        duration_seconds=7.5,
        steps=12,
        seed=1234,
    )

    state = build_control_desk_state(
        options,
        bundle,
        uploaded_files={
            r"D:\refs\hero.png": "ai_manga/h3/hero.png",
            r"D:\refs\lab.png": "ai_manga/h3/lab.png",
            r"D:\refs\motion.mp4": "ai_manga/h3/motion.mp4",
            r"D:\refs\voice.wav": "ai_manga/h3/voice.wav",
        },
        shot_meta={
            "prompt": "苏晚穿过冷蓝实验室，镜头缓慢推进。",
            "project": "归墟觉醒",
            "episode": 1,
            "scene": 2,
            "shot": 3,
            "take": 1,
        },
    )

    assert state["schema"] == "ltoj-manga/control-desk-v1.0"
    assert state["product_version"] == "3.1"
    assert state["director"]["mode"] == "Ref2VA"
    assert state["director"]["prompt_text"] == "苏晚穿过冷蓝实验室，镜头缓慢推进。"
    assert state["director"]["production"] == {
        "aspect_ratio": "9:16 竖屏",
        "resolution": "480p",
        "duration_seconds": 7.5,
        "steps": 12,
        "seed": 1234,
        "gpu_profile": "自动检测GPU",
        "model_profile": "standard",
        "reference_quality": "match",
        "scheduler": "官方基准（推荐先测）",
    }
    assert state["assets"]["images"][0] == {
        "filename": "ai_manga/h3/hero.png",
        "enabled": True,
        "role": "主角身份",
        "include_audio": False,
        "duration_seconds": 0.0,
        "bound_image_alias": "",
    }
    assert state["assets"]["images"][1]["enabled"] is False
    assert state["assets"]["images"][2]["filename"] == "ai_manga/h3/lab.png"
    assert state["assets"]["videos"][0]["include_audio"] is True
    assert state["assets"]["videos"][0]["duration_seconds"] == 4.5
    assert state["assets"]["audios"][0]["duration_seconds"] == 3.0
    assert state["director"]["shot"] == {
        "project": "归墟觉醒", "episode": 1, "scene": 2, "shot": 3, "take": 1
    }


def test_control_desk_workflow_is_a_single_public_node_with_json_state():
    state = build_control_desk_state(
        H3UnifiedOptions(mode=H3Mode.T2VA, runtime="control_desk", seed=77),
        H3ReferenceBundle(),
        uploaded_files={},
        shot_meta={"prompt": "城市远景，云层快速流动。"},
    )

    workflow = build_control_desk_workflow(state)

    assert workflow == {
        "1": {
            "class_type": CONTROL_DESK_NODE,
            "inputs": {"ui_state": workflow["1"]["inputs"]["ui_state"]},
        }
    }
    assert json.loads(workflow["1"]["inputs"]["ui_state"]) == state


def test_control_desk_state_requires_uploaded_relative_file_for_enabled_reference():
    bundle = H3ReferenceBundle(
        images=(H3ReferenceItem("image", H3ImageRole.CHARACTER_IDENTITY, r"D:\refs\hero.png"),)
    )

    with pytest.raises(ValueError, match="reference file is not uploaded"):
        build_control_desk_state(
            H3UnifiedOptions(mode=H3Mode.REF2VA),
            bundle,
            uploaded_files={},
            shot_meta={"prompt": "人物近景"},
        )


def test_control_desk_state_validates_fl2va_frames_before_building_state():
    options = H3UnifiedOptions(mode=H3Mode.FL2VA)

    with pytest.raises(ValueError, match="FL2VA requires first_frame and last_frame"):
        build_control_desk_state(
            options,
            H3ReferenceBundle(),
            uploaded_files={"first.png": "h3/first.png"},
            shot_meta={"prompt": "人物转身", "first_frame": "first.png"},
        )
