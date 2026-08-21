from backend.production.workflow_registry import (
    WAN22_WORKFLOW_MODE,
    select_wan_video_workflow,
)


def test_wan_workflow_registry_native_default_without_end_frame():
    spec = select_wan_video_workflow(has_end_frame=False)

    assert spec.name == "wan22_ti2v5b_native"
    assert spec.supports_end_frame is False


def test_wan_workflow_registry_wrapper_mode_uses_i2v():
    import backend.production.workflow_registry as reg
    old_mode = reg.WAN22_WORKFLOW_MODE
    try:
        reg.WAN22_WORKFLOW_MODE = "wrapper"
        spec = reg.select_wan_video_workflow(has_end_frame=False)
        assert spec.name == "wan22_i2v"
    finally:
        reg.WAN22_WORKFLOW_MODE = old_mode


def test_wan_workflow_registry_wrapper_mode_prefers_flf2v_when_end_frame_exists():
    import backend.production.workflow_registry as reg
    old_mode = reg.WAN22_WORKFLOW_MODE
    try:
        reg.WAN22_WORKFLOW_MODE = "wrapper"
        spec = reg.select_wan_video_workflow(has_end_frame=True)
        assert spec.name == "wan22_flf2v"
        assert spec.supports_end_frame is True
    finally:
        reg.WAN22_WORKFLOW_MODE = old_mode
