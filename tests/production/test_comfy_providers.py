from pathlib import Path

import pytest

from backend.production.comfy_image import FluxImageProvider
from backend.production.providers import ImageRequest
from backend.production.workflow_templates import WorkflowTemplate


class RecordingAdapter:
    def __init__(self):
        self.workflow = None

    async def generate_to_file(self, workflow, destination):
        self.workflow = workflow
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(b"generated-image")
        return object()


def _request(output: Path) -> ImageRequest:
    return ImageRequest(
        prompt="cinematic live-action harbor",
        negative_prompt="anime, manga",
        seed=42,
        width=768,
        height=1344,
        output_path=output,
    )


@pytest.mark.asyncio
async def test_flux_provider_binds_request_and_writes_requested_path(tmp_path: Path):
    adapter = RecordingAdapter()
    template = WorkflowTemplate.from_dict(
        {
            "workflow": {
                "2": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
                "3": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
                "4": {
                    "class_type": "EmptySD3LatentImage",
                    "inputs": {"width": 0, "height": 0},
                },
                "5": {"class_type": "KSampler", "inputs": {"seed": 0}},
                "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": ""}},
            },
            "bindings": {
                "prompt": ["2", "text"],
                "negative_prompt": ["3", "text"],
                "width": ["4", "width"],
                "height": ["4", "height"],
                "seed": ["5", "seed"],
                "filename_prefix": ["7", "filename_prefix"],
            },
        }
    )
    provider = FluxImageProvider(adapter=adapter, template=template)
    output = tmp_path / "shot_01" / "keyframe.png"

    artifact = await provider.generate(_request(output))

    assert artifact.path == output
    assert output.read_bytes() == b"generated-image"
    assert adapter.workflow["2"]["inputs"]["text"] == "cinematic live-action harbor"
    assert adapter.workflow["3"]["inputs"]["text"] == "anime, manga"
    assert adapter.workflow["4"]["inputs"]["width"] == 768
    assert adapter.workflow["5"]["inputs"]["seed"] == 42


@pytest.mark.asyncio
async def test_flux_provider_duplicates_prompts_for_flux_dual_encoder(tmp_path: Path):
    adapter = RecordingAdapter()
    template = WorkflowTemplate.from_dict(
        {
            "workflow": {
                "4": {
                    "class_type": "CLIPTextEncodeFlux",
                    "inputs": {"clip_l": "", "t5xxl": ""},
                },
                "5": {
                    "class_type": "CLIPTextEncodeFlux",
                    "inputs": {"clip_l": "", "t5xxl": ""},
                },
                "6": {
                    "class_type": "EmptySD3LatentImage",
                    "inputs": {"width": 0, "height": 0},
                },
                "7": {"class_type": "KSampler", "inputs": {"seed": 0}},
                "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": ""}},
            },
            "bindings": {
                "prompt": ["4", "clip_l"],
                "prompt_t5": ["4", "t5xxl"],
                "negative_prompt": ["5", "clip_l"],
                "negative_prompt_t5": ["5", "t5xxl"],
                "width": ["6", "width"],
                "height": ["6", "height"],
                "seed": ["7", "seed"],
                "filename_prefix": ["9", "filename_prefix"],
            },
        }
    )
    provider = FluxImageProvider(adapter=adapter, template=template)

    await provider.generate(_request(tmp_path / "keyframe.png"))

    assert adapter.workflow["4"]["inputs"]["clip_l"] == "cinematic live-action harbor"
    assert adapter.workflow["4"]["inputs"]["t5xxl"] == "cinematic live-action harbor"
    assert adapter.workflow["5"]["inputs"]["clip_l"] == "anime, manga"
    assert adapter.workflow["5"]["inputs"]["t5xxl"] == "anime, manga"
