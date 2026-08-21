from copy import deepcopy

from backend.production.h3_unified.continuity import MOTION_CONTEXT_NODE_SIGNATURES
from backend.production.preflight import inspect_object_info


def _node(required=(), optional=()):
    return {
        "input": {
            "required": {name: ["STRING"] for name in required},
            "optional": {name: ["STRING"] for name in optional},
        }
    }


def _motion_object_info():
    return {
        node_name: _node(signature["required"], signature["optional"])
        for node_name, signature in MOTION_CONTEXT_NODE_SIGNATURES.items()
    }


def test_control_desk_preflight_only_requires_public_bridge_node():
    report = inspect_object_info(
        {"LtoJ_H3UnifiedControlDesk": _node(required=("ui_state",))},
        provider="minimax_h3_control_desk",
    )

    assert report.ok is True
    assert report.missing == []
    assert next(check for check in report.checks if check.name == "h3_control_desk").ok is True


def test_control_desk_preflight_reports_missing_optional_runtime_without_breaking_other_h3_contracts():
    report = inspect_object_info({}, provider="minimax_h3_control_desk")

    assert report.ok is False
    assert report.missing == ["h3_control_desk"]


def test_motion_context_preflight_accepts_all_four_public_node_signatures():
    report = inspect_object_info(_motion_object_info(), provider="minimax_h3_motion_context")

    assert report.ok is True
    assert report.missing == []
    assert {check.name for check in report.checks} == {
        "h3_motion_context",
        "h3_motion_context_trim",
        "h3_motion_context_save_latent",
        "h3_motion_context_load_latent",
    }


def test_motion_context_preflight_rejects_missing_optional_context_latent_input():
    object_info = _motion_object_info()
    broken = deepcopy(object_info)
    del broken["MiniMaxH3MotionContext"]["input"]["optional"]["context_latent"]

    report = inspect_object_info(broken, provider="minimax_h3_motion_context")

    assert report.ok is False
    assert report.missing == ["h3_motion_context"]
    detail = next(check.detail for check in report.checks if check.name == "h3_motion_context")
    assert "context_latent" in detail
