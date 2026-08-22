from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from backend.novel_video.h3_frames import legal_h3_frames
from backend.novel_video.h3_unified_runtime import H3UnifiedSegmentRequest
from backend.novel_video.models import AssetVersion, AspectRatio, H3ReferencePackage
from backend.production.comfy_adapter import ProductionError
from backend.video.h3_unified.formal_provider import H3UnifiedFormalSegmentProvider


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _asset(asset_id: str, kind: str, path: Path) -> AssetVersion:
    return AssetVersion(
        id=asset_id,
        project_id="project-1",
        run_id="run-1",
        shot_id="shot-01",
        kind=kind,
        state="approved",
        path=path,
        sha256=_digest(path),
    )


def _request(tmp_path: Path):
    specs = (
        ("tail", "tail", "tail.png", b"tail"),
        ("character", "character", "character.png", b"character"),
        ("scene", "scene", "scene.png", b"scene"),
        ("motion", "video", "motion.mp4", b"motion"),
        ("voice", "dialogue_audio", "voice.wav", b"voice"),
    )
    assets = {}
    for asset_id, kind, filename, payload in specs:
        path = tmp_path / filename
        path.write_bytes(payload)
        assets[asset_id] = _asset(asset_id, kind, path)

    package = H3ReferencePackage(
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
        picture_asset_version_ids=["tail", "character", "scene"],
        video_reference_asset_version_ids=["motion"],
        audio_reference_asset_version_ids=["voice"],
        workflow_version="h3_unified",
        continuity_reason="same_action",
    )
    request = H3UnifiedSegmentRequest(
        package=package,
        picture_paths=(assets["tail"].path, assets["character"].path, assets["scene"].path),
        video_paths=(assets["motion"].path,),
        audio_paths=(assets["voice"].path,),
        output_video=tmp_path / "final.mp4",
        output_tail=tmp_path / "final-tail.png",
    )
    return request, assets


def _provider(assets):
    return H3UnifiedFormalSegmentProvider(
        asset_resolver=assets.get,
        task_binding={
            "task_id": "task-1",
            "run_id": "run-1",
            "shot_id": "shot-01",
            "attempt_id": "task-1:1",
        },
    )


def test_provider_maps_verified_media_and_binds_digests_into_checkpoint_and_manifest(tmp_path: Path) -> None:
    request, assets = _request(tmp_path)
    provider = _provider(assets)

    provider._validate_request_contract(request)
    unified = provider._to_unified_request(request)
    checkpoint = provider._checkpoint_binding(request)
    manifest = provider._publisher()._manifest_binding(request)

    assert unified.references.videos == (str(assets["motion"].path),)
    assert unified.references.audios == (str(assets["voice"].path),)
    assert checkpoint["video_inputs"] == [
        {"asset_id": "motion", "sha256": assets["motion"].sha256}
    ]
    assert checkpoint["audio_inputs"] == [
        {"asset_id": "voice", "sha256": assets["voice"].sha256}
    ]
    assert manifest["video_inputs"] == checkpoint["video_inputs"]
    assert manifest["audio_inputs"] == checkpoint["audio_inputs"]
    assert len(checkpoint["idempotency_hash"]) == 64
    assert len(manifest["idempotency_hash"]) == 64


def test_provider_rejects_media_bytes_changed_after_asset_approval(tmp_path: Path) -> None:
    request, assets = _request(tmp_path)
    provider = _provider(assets)
    assets["motion"].path.write_bytes(b"changed-after-approval")

    with pytest.raises(ProductionError, match="bytes no longer match approved asset"):
        provider._validate_request_contract(request)
