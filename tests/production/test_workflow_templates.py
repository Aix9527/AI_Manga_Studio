import copy

import pytest

from backend.production.workflow_templates import WorkflowTemplate


def test_template_injects_image_prompt_seed_size_and_frames():
    template = WorkflowTemplate.from_dict(
        {
            "workflow": {
                "10": {"inputs": {"image": ""}, "class_type": "LoadImage"},
                "20": {"inputs": {"text": ""}, "class_type": "CLIPTextEncode"},
                "30": {
                    "inputs": {"seed": 0, "width": 0, "height": 0, "length": 0},
                    "class_type": "EmptyLTXVLatentVideo",
                },
            },
            "bindings": {
                "image": ["10", "image"],
                "prompt": ["20", "text"],
                "seed": ["30", "seed"],
                "width": ["30", "width"],
                "height": ["30", "height"],
                "frames": ["30", "length"],
            },
        }
    )

    workflow = template.render(
        image="shot.png",
        prompt="live-action harbor at night",
        seed=42,
        width=432,
        height=768,
        frames=97,
    )

    assert workflow["10"]["inputs"]["image"] == "shot.png"
    assert workflow["20"]["inputs"]["text"] == "live-action harbor at night"
    assert workflow["30"]["inputs"] == {
        "seed": 42,
        "width": 432,
        "height": 768,
        "length": 97,
    }


def test_render_does_not_mutate_template():
    payload = {
        "workflow": {"1": {"inputs": {"seed": 0}, "class_type": "RandomNoise"}},
        "bindings": {"seed": ["1", "seed"]},
    }
    original = copy.deepcopy(payload)
    template = WorkflowTemplate.from_dict(payload)

    template.render(seed=99)

    assert payload == original


def test_template_rejects_unknown_binding_node():
    with pytest.raises(ValueError, match="node 999"):
        WorkflowTemplate.from_dict(
            {
                "workflow": {"1": {"inputs": {}, "class_type": "LoadImage"}},
                "bindings": {"image": ["999", "image"]},
            }
        )
