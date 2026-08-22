from __future__ import annotations

from dataclasses import fields

from fastapi import APIRouter

from backend.core.runtime.providers.h3 import H3Provider
from backend.core.runtime.router import ModelRouter
from backend.core.runtime.scheduler import scheduler
from backend.core.runtime.workflow_registry import WorkflowRegistry
from backend.production.comfy_adapter import ComfyUIAdapter
from backend.video.h3_unified.reference_bundle import H3ReferenceBundle
from backend.video.h3_unified.segmented import H3SegmentPolicy, build_segment_plan
from backend.video.h3_unified.ui_state import H3Mode, H3UnifiedRequest, build_ui_state
from backend.video.providers.minimax_h3_unified_provider import H3UnifiedProvider


router = APIRouter()


def _reference_bundle_from_mapping(value: dict | None) -> H3ReferenceBundle:
    payload = dict(value or {})
    allowed = set(H3ReferenceBundle.IMAGE_FIELDS) | {"videos", "audios"}
    filtered = {key: item for key, item in payload.items() if key in allowed}
    if "videos" in filtered:
        filtered["videos"] = tuple(filtered["videos"] or ())
    if "audios" in filtered:
        filtered["audios"] = tuple(filtered["audios"] or ())
    return H3ReferenceBundle(**filtered)


def _unified_request_from_mapping(body: dict) -> H3UnifiedRequest:
    payload = dict(body or {})
    allowed = {item.name for item in fields(H3UnifiedRequest)}
    request_values = {key: value for key, value in payload.items() if key in allowed}
    request_values["references"] = _reference_bundle_from_mapping(payload.get("references"))
    if "mode" in request_values and not isinstance(request_values["mode"], H3Mode):
        request_values["mode"] = H3Mode(str(request_values["mode"]))
    return H3UnifiedRequest(**request_values)


@router.post("/route")
def route(body: dict):
    return ModelRouter().select(body)


@router.post("/h3/prompt")
def h3_prompt(body: dict):
    return H3Provider().build_prompt(body)


@router.get("/h3/validate")
def h3_validate():
    return H3Provider().validate(
        {
            "workflow": "standard",
            "profile": "production",
        }
    )


@router.get("/h3/unified/preflight")
async def h3_unified_preflight():
    """Inspect the live local ComfyUI node catalogue for optional H3 capabilities."""

    object_info = await ComfyUIAdapter().get_object_info()
    return H3UnifiedProvider().preflight(object_info)


@router.post("/h3/unified/state")
def h3_unified_state(body: dict):
    """Build the stable first-party H3 unified control state.

    This endpoint does not require the optional external ComfyUI node to be
    installed; callers can prepare and persist the state before live preflight.
    """

    return build_ui_state(_unified_request_from_mapping(body))


@router.post("/h3/segments/plan")
def h3_segment_plan(body: dict):
    """Build a provider-neutral long-video H3 segment/V6 continuity plan."""

    payload = dict(body or {})
    policy_fields = {item.name for item in fields(H3SegmentPolicy)}
    policy_values = {
        key: value
        for key, value in payload.items()
        if key in policy_fields
    }
    policy = H3SegmentPolicy(**policy_values)
    plan = build_segment_plan(
        total_duration_seconds=float(payload["total_duration_seconds"]),
        global_prompt=str(payload.get("prompt", payload.get("global_prompt", ""))),
        segment_prompts=tuple(payload.get("segment_prompts") or ()),
        policy=policy,
        motion_context_available=bool(payload.get("motion_context_available", False)),
        run_name=str(payload.get("run_name", "h3_segmented")),
    )
    return plan.to_dict()


@router.get("/workflows")
def workflows():
    return WorkflowRegistry().list()


@router.post("/vram/acquire")
def vram_acquire(body: dict):
    ok = scheduler.acquire(body.get("required", 12))
    return {"granted": ok}


@router.post("/vram/release")
def vram_release():
    scheduler.release()
    return {"released": True}
