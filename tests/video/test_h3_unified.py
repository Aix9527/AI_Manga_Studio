from __future__ import annotations

import json

import pytest

from backend.video.h3_unified.reference_bundle import H3ReferenceBundle
from backend.video.h3_unified.segmented import H3SegmentPolicy, build_segment_plan
from backend.video.h3_unified.ui_state import H3Mode, H3UnifiedRequest, build_ui_state
from backend.video.providers.minimax_h3_unified_provider import H3UnifiedProvider


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


def test_unified_request_defaults_to_valid_control_desk_camera_movement() -> None:
    # 总控台 LtoJ_H3UnifiedControlDesk 的 CAMERA_MOVEMENT_CHOICES 首个合法值为
    # "自动/未指定"; "固定镜头" 不在枚举中, 会触发 "不支持的运镜" 执行错误。
    request = H3UnifiedRequest(mode=H3Mode.T2VA, prompt="test")
    state = build_ui_state(request)
    assert state["director"]["camera"]["movement"] == "自动/未指定"


def test_unified_request_rejects_invalid_duration_and_step_count() -> None:
    with pytest.raises(ValueError, match="2.*15"):
        H3UnifiedRequest(mode=H3Mode.T2VA, prompt="test", duration_seconds=16)

    with pytest.raises(ValueError, match="steps"):
        H3UnifiedRequest(mode=H3Mode.T2VA, prompt="test", steps=9)


def test_segment_plan_rebalances_short_tail_and_maps_segment_prompts() -> None:
    plan = build_segment_plan(
        total_duration_seconds=32,
        global_prompt="global",
        segment_prompts=("p1", "p2", "p3", "p4"),
        policy=H3SegmentPolicy(segment_seconds=10, gpu_vram_gb=16),
        motion_context_available=True,
        run_name="gx_ep01_shot03",
    )

    assert [segment.duration_seconds for segment in plan.segments] == [10, 10, 7, 5]
    assert [segment.prompt for segment in plan.segments] == ["p1", "p2", "p3", "p4"]
    assert plan.continuity == "latent"
    assert plan.dual_sample is False
    assert plan.super_resolution_scale == 1.5
    assert plan.segments[1].load_previous_latent is True
    assert plan.segments[0].load_previous_latent is False
    assert plan.segments[-1].latent_output.endswith("clip_00004.safetensors")


def test_segment_plan_falls_back_to_frame_continuity_without_motion_context_nodes() -> None:
    plan = build_segment_plan(
        total_duration_seconds=18,
        global_prompt="global",
        policy=H3SegmentPolicy(segment_seconds=10, continuity="auto", gpu_vram_gb=16),
        motion_context_available=False,
    )

    assert [segment.duration_seconds for segment in plan.segments] == [10, 8]
    assert plan.continuity == "frame_reference"
    assert all(segment.load_previous_latent is False for segment in plan.segments)


def test_segment_policy_allows_dual_sample_only_as_explicit_opt_in() -> None:
    default_policy = H3SegmentPolicy(gpu_vram_gb=16)
    dual_policy = H3SegmentPolicy(gpu_vram_gb=16, dual_sample=True)

    assert default_policy.dual_sample is False
    assert dual_policy.dual_sample is True


def test_provider_preflight_detects_external_unified_and_v6_motion_context_nodes() -> None:
    object_info = {
        "LtoJ_H3UnifiedControlDesk": {},
        "MiniMaxH3MotionContextLoadLatent": {},
        "MiniMaxH3MotionContext": {},
        "MiniMaxH3MotionContextTrim": {},
        "MiniMaxH3MotionContextSaveLatent": {},
    }

    status = H3UnifiedProvider().preflight(object_info)

    assert status["external_unified_available"] is True
    assert status["latent_continuity_available"] is True
    assert status["recommended_runtime"] == "external_unified"
    assert status["transparent_fallback_available"] is False
    assert status["missing_motion_context_nodes"] == []


def test_provider_preflight_marks_unified_unavailable_instead_of_claiming_native_fallback() -> None:
    status = H3UnifiedProvider().preflight({"MiniMaxH3ReferenceToVideo": {}})

    assert status["external_unified_available"] is False
    assert status["recommended_runtime"] == "unavailable"
    assert status["transparent_fallback_available"] is False
    assert status["alternate_route"] == "h3/reference"
    assert status["alternate_route_requires_recompile"] is True
    assert "LtoJ_H3UnifiedControlDesk" in status["missing_nodes"]


def test_provider_builds_single_node_external_workflow_with_serialized_ui_state() -> None:
    request = H3UnifiedRequest(
        mode=H3Mode.FL2VA,
        prompt="人物向镜头冲来",
        first_frame="first.png",
        last_frame="last.png",
        duration_seconds=6,
    )

    workflow = H3UnifiedProvider().build_external_workflow(request)

    assert workflow["1"]["class_type"] == "LtoJ_H3UnifiedControlDesk"
    state = json.loads(workflow["1"]["inputs"]["ui_state"])
    assert state["director"]["mode"] == "FL2VA"
    assert state["assets"]["first_frame"]["filename"] == "first.png"
    assert state["assets"]["last_frame"]["filename"] == "last.png"
