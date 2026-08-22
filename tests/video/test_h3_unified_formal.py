from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.novel_video.h3_frames import legal_h3_frames
from backend.novel_video.h3_provider import H3SegmentRequest
from backend.novel_video.models import AspectRatio, H3ReferencePackage
from backend.video.h3_unified.execution import H3UnifiedExecutionResult
from backend.video.h3_unified.formal_provider import H3UnifiedFormalSegmentProvider


class FakeExecutionService:
    def __init__(self) -> None:
        self.calls = []

    async def execute(self, request, **kwargs):
        self.calls.append((request, kwargs))
        callback = kwargs.get("on_submitted")
        prompt_id = kwargs.get("resume_prompt_id") or "prompt-new"
        if callback and not kwargs.get("resume_prompt_id"):
            outcome = callback(prompt_id)
            if hasattr(outcome, "__await__"):
                await outcome
        return H3UnifiedExecutionResult(
            prompt_id=prompt_id,
            outputs={"1": {"videos": [{"filename": "out.mp4"}]}},
            runtime="external_unified",
            resumed=bool(kwargs.get("resume_prompt_id")),
        )


class FakeMediaAdapter:
    def first_artifact(self, outputs):
        return SimpleNamespace(filename="out.mp4", subfolder="", type="output", media_kind="videos")

    async def download_artifact(self, artifact):
        return b"video-bytes"


def _package() -> H3ReferencePackage:
    return H3ReferencePackage(
        shot_id="shot-01",
        prompt_version="h3-unified-v1",
        prompt_text="雨夜走廊追逐",
        negative_prompt="static",
        base_seed=7,
        effective_seed=11,
        duration_seconds=5,
        legal_frame_count=legal_h3_frames(5),
        width=480,
        height=832,
        aspect_ratio=AspectRatio.PORTRAIT,
        picture_asset_version_ids=["pic-tail", "pic-char", "pic-scene"],
        video_reference_asset_version_ids=[],
        audio_reference_asset_version_ids=[],
        workflow_version="h3_unified",
        continuity_reason="same_action",
    )


def _segment_request(tmp_path: Path) -> H3SegmentRequest:
    picture_paths = (
        tmp_path / "tail.png",
        tmp_path / "character.png",
        tmp_path / "scene.png",
    )
    for path in picture_paths:
        path.write_bytes(b"approved-picture")
    return H3SegmentRequest(
        package=_package(),
        picture_paths=picture_paths,
        output_video=tmp_path / "final.mp4",
        output_tail=tmp_path / "tail-out.png",
    )


@pytest.mark.asyncio
async def test_formal_provider_maps_approved_picture_package_to_unified_request_and_checkpoints_identity(tmp_path: Path, monkeypatch) -> None:
    execution = FakeExecutionService()
    provider = H3UnifiedFormalSegmentProvider(
        adapter=FakeMediaAdapter(),
        execution=execution,
        task_binding={
            "task_id": "task-1",
            "run_id": "run-1",
            "shot_id": "shot-01",
            "attempt_id": "task-1:1",
        },
    )
    checkpointed = []
    provider.on_prompt_submitted = lambda prompt_id, checkpoint=None: checkpointed.append((prompt_id, checkpoint))
    expected = SimpleNamespace(
        prompt_id="prompt-new",
        video_path=tmp_path / "final.mp4",
        tail_frame_path=tmp_path / "tail-out.png",
    )

    async def fake_materialize(result, request):
        return expected

    monkeypatch.setattr(provider, "_materialize", fake_materialize)
    result = await provider.generate(_segment_request(tmp_path))

    unified_request, kwargs = execution.calls[0]
    assert unified_request.references.character_identity == str(tmp_path / "character.png")
    assert unified_request.references.location == str(tmp_path / "scene.png")
    assert unified_request.references.storyboard == str(tmp_path / "tail.png")
    assert unified_request.references.videos == ()
    assert unified_request.references.audios == ()
    assert unified_request.first_frame == str(tmp_path / "tail.png")
    assert kwargs["subfolder"].startswith("h3_unified/formal/")
    assert result is expected
    assert checkpointed[0][0] == "prompt-new"
    assert checkpointed[0][1]["task_id"] == "task-1"
    assert checkpointed[0][1]["shot_id"] == "shot-01"
    assert checkpointed[0][1]["prompt_id"] == "prompt-new"


@pytest.mark.asyncio
async def test_formal_provider_resume_uses_exact_prompt_without_new_checkpoint(tmp_path: Path, monkeypatch) -> None:
    execution = FakeExecutionService()
    provider = H3UnifiedFormalSegmentProvider(
        adapter=FakeMediaAdapter(),
        execution=execution,
        task_binding={
            "task_id": "task-1",
            "run_id": "run-1",
            "shot_id": "shot-01",
            "attempt_id": "task-1:1",
        },
    )
    callbacks = []
    provider.on_prompt_submitted = lambda *args: callbacks.append(args)
    expected = SimpleNamespace(
        prompt_id="prompt-existing",
        video_path=tmp_path / "final.mp4",
        tail_frame_path=tmp_path / "tail-out.png",
    )

    async def fake_materialize(result, request):
        return expected

    monkeypatch.setattr(provider, "_materialize", fake_materialize)
    checkpoint = {
        "task_id": "task-1",
        "run_id": "run-1",
        "shot_id": "shot-01",
        "attempt_id": "task-1:1",
        "prompt_id": "prompt-existing",
    }
    result = await provider.resume(_segment_request(tmp_path), "prompt-existing", checkpoint)

    assert result is expected
    assert execution.calls[0][1]["resume_prompt_id"] == "prompt-existing"
    assert callbacks == []


def test_formal_provider_rejects_resume_checkpoint_identity_mismatch(tmp_path: Path) -> None:
    provider = H3UnifiedFormalSegmentProvider(
        adapter=FakeMediaAdapter(),
        execution=FakeExecutionService(),
        task_binding={
            "task_id": "task-1",
            "run_id": "run-1",
            "shot_id": "shot-01",
            "attempt_id": "task-1:1",
        },
    )
    checkpoint = {
        "task_id": "other-task",
        "run_id": "run-1",
        "shot_id": "shot-01",
        "attempt_id": "task-1:1",
        "prompt_id": "prompt-existing",
    }

    with pytest.raises(ValueError, match="identity"):
        provider._validate_resume_checkpoint("prompt-existing", checkpoint)
