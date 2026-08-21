from pathlib import Path

from backend.production.workflow_templates import WorkflowTemplate


def test_live_workflow_uses_flux2_klein_4b_distilled_graph():
    root = Path(__file__).resolve().parents[2]
    template = WorkflowTemplate.load(
        root / "backend" / "production" / "workflows" / "flux_live_action.json"
    )

    workflow = template.render(
        prompt="cinematic laboratory",
        seed=20260727,
        width=512,
        height=896,
        filename_prefix="novel_video/keyframe",
    )

    assert workflow["1"] == {
        "class_type": "UNETLoader",
        "inputs": {
            "unet_name": "flux-2-klein-4b-fp8.safetensors",
            "weight_dtype": "default",
        },
    }
    assert workflow["2"]["inputs"] == {
        "clip_name": "qwen_3_4b.safetensors",
        "type": "flux2",
        "device": "default",
    }
    assert workflow["3"]["inputs"]["vae_name"] == "flux2-vae.safetensors"
    assert workflow["5"]["class_type"] == "ConditioningZeroOut"
    assert workflow["8"]["inputs"]["cfg"] == 1.0
    assert workflow["10"]["inputs"]["steps"] == 4
    assert workflow["6"]["inputs"]["width"] == 512
    assert workflow["10"]["inputs"]["width"] == 512
    assert workflow["6"]["inputs"]["height"] == 896
    assert workflow["10"]["inputs"]["height"] == 896
    assert "negative_prompt" not in template.bindings
