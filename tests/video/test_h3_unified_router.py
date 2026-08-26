from __future__ import annotations

import pytest

import backend.api.runtime_api as runtime_api
from backend.api.runtime_api import h3_segment_plan, h3_unified_preflight, h3_unified_state
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
    assert selected["fallback"] is None
    assert selected["alternate_route"] == "h3/reference"
    assert selected["alternate_route_requires_recompile"] is True


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


@pytest.mark.asyncio
async def test_runtime_preflight_reads_live_comfy_node_catalogue(monkeypatch) -> None:
    async def fake_object_info(self):
        return {
            "LtoJ_H3UnifiedControlDesk": {},
            "MiniMaxH3MotionContextLoadLatent": {},
            "MiniMaxH3MotionContext": {},
            "MiniMaxH3MotionContextTrim": {},
            "MiniMaxH3MotionContextSaveLatent": {},
        }

    monkeypatch.setattr(runtime_api.ComfyUIAdapter, "get_object_info", fake_object_info)

    status = await h3_unified_preflight()

    assert status["external_unified_available"] is True
    assert status["latent_continuity_available"] is True
    assert status["recommended_runtime"] == "external_unified"


@pytest.mark.asyncio
async def test_runtime_preflight_does_not_claim_native_unified_when_control_node_is_missing(monkeypatch) -> None:
    async def fake_object_info(self):
        return {"MiniMaxH3ReferenceToVideo": {}}

    monkeypatch.setattr(runtime_api.ComfyUIAdapter, "get_object_info", fake_object_info)

    status = await h3_unified_preflight()

    assert status["external_unified_available"] is False
    assert status["recommended_runtime"] == "unavailable"
    assert status["alternate_route"] == "h3/reference"
    assert status["alternate_route_requires_recompile"] is True
