from __future__ import annotations

from backend.api.runtime_api import h3_segment_plan, h3_unified_state
from backend.core.runtime.router import ModelRouter


def test_router_selects_unified_h3_only_when_explicitly_requested() -> None:
    selected = ModelRouter().select(
        {
            "stage": "video_generation",
            "h3_unified": True,
            "intent": "long_reference",
            "ref_count": 4,
        }
    )

    assert selected["provider"] == "h3"
    assert selected["model"] == "minimax_h3_unified"
    assert selected["workflow"] == "unified"
    assert selected["fallback"] == "h3/reference"


def test_router_preserves_existing_reference_route_without_unified_opt_in() -> None:
    selected = ModelRouter().select(
        {
            "stage": "video_generation",
            "intent": "reference",
            "ref_count": 4,
        }
    )

    assert selected["provider"] == "h3"
    assert selected["model"] == "minimax_h3_ref2va"
    assert selected["workflow"] == "reference"


def test_runtime_api_builds_unified_state_from_plain_mapping() -> None:
    state = h3_unified_state(
        {
            "mode": "Ref2VA",
            "prompt": "苏晚冲过雨夜走廊",
            "references": {
                "character_identity": "suwan.png",
                "location": "lab.png",
                "lighting": "rain.png",
            },
            "duration_seconds": 5,
            "steps": 12,
            "gpu_vram_gb": 16,
        }
    )

    assert state["director"]["mode"] == "Ref2VA"
    assert state["runtime"]["profile"] == "balanced_offload_16gb"
    assert state["assets"]["images"][0]["filename"] == "suwan.png"


def test_runtime_api_builds_segment_plan_with_frame_fallback() -> None:
    plan = h3_segment_plan(
        {
            "total_duration_seconds": 22,
            "prompt": "持续追逐",
            "segment_seconds": 10,
            "gpu_vram_gb": 16,
            "motion_context_available": False,
        }
    )

    assert [item["duration_seconds"] for item in plan["segments"]] == [10, 7, 5]
    assert plan["continuity"] == "frame_reference"
    assert plan["dual_sample"] is False
