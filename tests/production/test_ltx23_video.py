from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend.production.comfy_adapter import ProductionError, ProductionErrorCode
from backend.production.providers import VideoRequest
from backend.production.workflow_templates import WorkflowTemplate


class UploadedImage:
    reference = "novel_video/keyframe.png"


class UploadedEndImage:
    reference = "novel_video/end_frame.png"


class RecordingAdapter:
    def __init__(self):
        self.uploaded_path: Path | None = None
        self.uploaded_paths: list[Path] = []
        self.workflow = None

    async def upload_image(self, image_path):
        self.uploaded_path = Path(image_path)
        self.uploaded_paths.append(Path(image_path))
        if Path(image_path).name == "end.png":
            return UploadedEndImage()
        return UploadedImage()

    async def generate_to_file(self, workflow, destination):
        self.workflow = workflow
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"generated-video")
        return type("Artifact", (), {"filename": "shot_01_00001.mp4"})()


def _request(image: Path, output: Path) -> VideoRequest:
    return VideoRequest(
        image_path=image,
        prompt="A scientist turns toward the camera as lab lights pulse.",
        negative_prompt="still frame, low quality",
        seed=20260727,
        width=432,
        height=768,
        frames=25,
        fps=24,
        output_path=output,
    )


@pytest.mark.asyncio
async def test_ltx_provider_uploads_keyframe_binds_request_and_writes_video(
    tmp_path: Path,
):
    from backend.production.comfy_video import LtxVideoProvider

    image = tmp_path / "keyframe.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    output = tmp_path / "output" / "shot_01.mp4"
    template = WorkflowTemplate.load(
        Path(__file__).parents[2]
        / "backend"
        / "production"
        / "workflows"
        / "ltx23_i2v.json"
    )
    adapter = RecordingAdapter()

    artifact = await LtxVideoProvider(adapter=adapter, template=template).generate(
        _request(image, output)
    )

    assert artifact.path == output
    assert artifact.kind == "video"
    assert output.read_bytes() == b"generated-video"
    assert adapter.uploaded_path == image
    assert adapter.workflow["1"]["inputs"]["image"] == "novel_video/keyframe.png"
    assert adapter.workflow["5"]["inputs"]["text"] == (
        "A scientist turns toward the camera as lab lights pulse."
    )
    assert adapter.workflow["6"]["inputs"]["text"] == "still frame, low quality"
    assert adapter.workflow["7"]["inputs"]["width"] == 432
    assert adapter.workflow["7"]["inputs"]["height"] == 768
    assert adapter.workflow["7"]["inputs"]["length"] == 25
    assert adapter.workflow["9"]["inputs"]["noise_seed"] == 20260727
    assert adapter.workflow["12"]["inputs"]["fps"] == 24
    assert adapter.workflow["13"]["inputs"]["filename_prefix"] == (
        "novel_video/shot_01"
    )
    assert artifact.metadata["uploaded_image"] == "novel_video/keyframe.png"


@pytest.mark.asyncio
async def test_ltx_provider_rejects_missing_keyframe_before_upload(tmp_path: Path):
    from backend.production.comfy_video import LtxVideoProvider

    adapter = RecordingAdapter()
    template = WorkflowTemplate.load(
        Path(__file__).parents[2]
        / "backend"
        / "production"
        / "workflows"
        / "ltx23_i2v.json"
    )

    with pytest.raises(ProductionError) as captured:
        await LtxVideoProvider(adapter=adapter, template=template).generate(
            _request(tmp_path / "missing.png", tmp_path / "shot.mp4")
        )

    assert captured.value.code is ProductionErrorCode.MEDIA_VALIDATION_FAILED
    assert adapter.uploaded_path is None
    assert adapter.workflow is None


@pytest.mark.asyncio
async def test_wan_flf2v_provider_uploads_first_and_last_frame(tmp_path: Path):
    from backend.production.comfy_video import WanVideoProvider

    first = tmp_path / "first.png"
    end = tmp_path / "end.png"
    first.write_bytes(b"\x89PNG\r\n\x1a\nfirst")
    end.write_bytes(b"\x89PNG\r\n\x1a\nend")
    output = tmp_path / "shot_flf2v.mp4"
    template = WorkflowTemplate.load(
        Path(__file__).parents[2]
        / "backend"
        / "production"
        / "workflows"
        / "wan22_flf2v.json"
    )
    adapter = RecordingAdapter()
    request = _request(first, output)
    request = VideoRequest(
        image_path=request.image_path,
        prompt=request.prompt,
        negative_prompt=request.negative_prompt,
        seed=request.seed,
        width=request.width,
        height=request.height,
        frames=request.frames,
        fps=request.fps,
        output_path=request.output_path,
        end_frame_path=str(end),
    )

    artifact = await WanVideoProvider(adapter=adapter, template=template).generate(request)

    assert artifact.path == output
    assert adapter.uploaded_paths == [first, end]
    assert adapter.workflow["1"]["inputs"]["image"] == "novel_video/keyframe.png"
    assert adapter.workflow["2"]["inputs"]["image"] == "novel_video/end_frame.png"
    assert artifact.metadata["flf2v_mode"] is True
    assert artifact.metadata["end_frame_image"] == "novel_video/end_frame.png"


def test_direct_ltx_smoke_reports_missing_models_before_queueing(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["LTX23_MODEL_ROOT"] = str(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "smoke_local_media.py"),
            "--provider",
            "ltx23",
            "--width",
            "432",
            "--height",
            "768",
            "--frames",
            "25",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode != 0
    assert "ltx-2.3-22b-distilled_transformer_only_fp8_input_scaled.safetensors" in (
        result.stderr
    )
    assert str(tmp_path) in result.stderr
