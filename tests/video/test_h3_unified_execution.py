from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.production.comfy_adapter import ComfyCompletedWorkflow, ComfyImageReference
from backend.video.h3_unified.comfy_media import H3ComfyMediaAdapter
from backend.video.h3_unified.execution import H3UnifiedExecutionService, H3UnifiedUnavailableError
from backend.video.h3_unified.reference_bundle import H3ReferenceBundle
from backend.video.h3_unified.staging import stage_h3_unified_request
from backend.video.h3_unified.ui_state import H3Mode, H3UnifiedRequest
from backend.video.providers.minimax_h3_unified_provider import (
    MOTION_CONTEXT_NODES,
    UNIFIED_CONTROL_NODE,
)


class FakeComfyAdapter:
    def __init__(self, *, external_available: bool = True) -> None:
        self.external_available = external_available
        self.uploads: list[tuple[str, str, str]] = []
        self.submitted: list[dict] = []
        self.waited: list[str] = []

    async def get_object_info(self) -> dict:
        if not self.external_available:
            return {}
        return {UNIFIED_CONTROL_NODE: {}, **{node: {} for node in MOTION_CONTEXT_NODES}}

    async def upload_image(self, path: str | Path, subfolder: str = "novel_video") -> ComfyImageReference:
        return self._record("image", path, subfolder)

    async def upload_video(self, path: str | Path, subfolder: str = "novel_video") -> ComfyImageReference:
        return self._record("video", path, subfolder)

    async def upload_audio(self, path: str | Path, subfolder: str = "novel_video") -> ComfyImageReference:
        return self._record("audio", path, subfolder)

    def _record(self, kind: str, path: str | Path, subfolder: str) -> ComfyImageReference:
        filename = Path(path).name
        self.uploads.append((kind, filename, subfolder))
        return ComfyImageReference(filename=filename, subfolder=subfolder)

    async def submit_and_wait(self, workflow: dict, on_submitted=None) -> ComfyCompletedWorkflow:
        self.submitted.append(workflow)
        prompt_id = "prompt-new"
        if on_submitted is not None:
            result = on_submitted(prompt_id)
            if hasattr(result, "__await__"):
                await result
        return ComfyCompletedWorkflow(prompt_id=prompt_id, outputs={"1": {"videos": [{"filename": "out.mp4"}]}})

    async def wait_for_completion(self, prompt_id: str) -> dict:
        self.waited.append(prompt_id)
        return {"1": {"videos": [{"filename": "resumed.mp4"}]}}


def _request(tmp_path: Path) -> H3UnifiedRequest:
    for name in ("character.png", "location.png", "motion.mp4", "voice.wav", "first.png", "last.png"):
        (tmp_path / name).write_bytes(b"media")
    return H3UnifiedRequest(
        mode=H3Mode.REF2VA,
        prompt="苏晚在暴雨实验楼走廊奔跑，镜头跟拍。",
        references=H3ReferenceBundle(
            character_identity=str(tmp_path / "character.png"),
            location=str(tmp_path / "location.png"),
            videos=(str(tmp_path / "motion.mp4"),),
            audios=(str(tmp_path / "voice.wav"),),
        ),
        first_frame=str(tmp_path / "first.png"),
        last_frame=str(tmp_path / "last.png"),
        duration_seconds=5,
        gpu_vram_gb=16,
    )


@pytest.mark.asyncio
async def test_staging_rewrites_local_media_to_comfy_input_references(tmp_path: Path) -> None:
    adapter = FakeComfyAdapter()
    original = _request(tmp_path)

    staged = await stage_h3_unified_request(original, adapter, subfolder="h3/gx_ep01_shot03")

    assert staged.references.character_identity == "h3/gx_ep01_shot03/character.png"
    assert staged.references.location == "h3/gx_ep01_shot03/location.png"
    assert staged.references.videos == ("h3/gx_ep01_shot03/motion.mp4",)
    assert staged.references.audios == ("h3/gx_ep01_shot03/voice.wav",)
    assert staged.first_frame == "h3/gx_ep01_shot03/first.png"
    assert staged.last_frame == "h3/gx_ep01_shot03/last.png"
    assert original.references.character_identity == str(tmp_path / "character.png")
    assert [kind for kind, _, _ in adapter.uploads] == [
        "image",
        "image",
        "video",
        "audio",
        "image",
        "image",
    ]


@pytest.mark.asyncio
async def test_staging_uploads_same_local_source_once_and_reuses_reference(tmp_path: Path) -> None:
    tail = tmp_path / "tail.png"
    tail.write_bytes(b"tail")
    adapter = FakeComfyAdapter()
    request = H3UnifiedRequest(
        mode=H3Mode.REF2VA,
        prompt="连续动作",
        references=H3ReferenceBundle(storyboard=str(tail)),
        first_frame=str(tail),
        duration_seconds=5,
    )

    staged = await stage_h3_unified_request(request, adapter, subfolder="h3/continuity")

    assert staged.references.storyboard == "h3/continuity/tail.png"
    assert staged.first_frame == "h3/continuity/tail.png"
    assert adapter.uploads == [("image", "tail.png", "h3/continuity")]


@pytest.mark.asyncio
async def test_h3_media_adapter_exposes_video_and_audio_uploads_via_generic_input_route(monkeypatch) -> None:
    adapter = H3ComfyMediaAdapter()
    calls: list[tuple[str, str, str]] = []

    async def fake_upload_input(path, subfolder="novel_video", *, media_kind="file"):
        calls.append((media_kind, Path(path).name, subfolder))
        return ComfyImageReference(filename=Path(path).name, subfolder=subfolder)

    monkeypatch.setattr(adapter, "upload_input", fake_upload_input, raising=False)

    video = await adapter.upload_video("motion.mp4", "h3")
    audio = await adapter.upload_audio("voice.wav", "h3")

    assert video.reference == "h3/motion.mp4"
    assert audio.reference == "h3/voice.wav"
    assert calls == [("video", "motion.mp4", "h3"), ("audio", "voice.wav", "h3")]


@pytest.mark.asyncio
async def test_execution_stages_assets_builds_external_workflow_and_checkpoints_prompt_id(tmp_path: Path) -> None:
    adapter = FakeComfyAdapter()
    checkpointed: list[str] = []
    service = H3UnifiedExecutionService(adapter=adapter)

    result = await service.execute(
        _request(tmp_path),
        subfolder="h3/gx_ep01_shot03",
        on_submitted=checkpointed.append,
    )

    assert result.prompt_id == "prompt-new"
    assert result.runtime == "external_unified"
    assert checkpointed == ["prompt-new"]
    assert len(adapter.submitted) == 1
    state = json.loads(adapter.submitted[0]["1"]["inputs"]["ui_state"])
    assert state["assets"]["images"][0]["filename"] == "h3/gx_ep01_shot03/character.png"
    assert state["assets"]["videos"][0]["filename"] == "h3/gx_ep01_shot03/motion.mp4"
    assert state["assets"]["audios"][0]["filename"] == "h3/gx_ep01_shot03/voice.wav"


@pytest.mark.asyncio
async def test_execution_resumes_existing_prompt_without_upload_or_resubmit(tmp_path: Path) -> None:
    adapter = FakeComfyAdapter()
    service = H3UnifiedExecutionService(adapter=adapter)

    result = await service.execute(_request(tmp_path), resume_prompt_id="prompt-existing")

    assert result.prompt_id == "prompt-existing"
    assert result.resumed is True
    assert adapter.waited == ["prompt-existing"]
    assert adapter.uploads == []
    assert adapter.submitted == []


@pytest.mark.asyncio
async def test_execution_rejects_external_submit_when_unified_node_is_missing(tmp_path: Path) -> None:
    adapter = FakeComfyAdapter(external_available=False)
    service = H3UnifiedExecutionService(adapter=adapter)

    with pytest.raises(H3UnifiedUnavailableError) as captured:
        await service.execute(_request(tmp_path))

    assert captured.value.alternate_route == "h3/reference"
    assert captured.value.fallback == "h3/reference"
    assert captured.value.requires_recompile is True
    assert adapter.uploads == []
    assert adapter.submitted == []
