from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

import pytest
import subprocess

from backend.novel_video.h3_provider import H3Ref2VASegmentProvider, H3SegmentRequest
from backend.novel_video.models import AssetVersion, AspectRatio, H3ReferencePackage
from backend.novel_video.storage import AtomicAssetStore
from backend.production.comfy_adapter import ComfyUIAdapter, ProductionError, ProductionErrorCode
from backend.production.workflow_templates import WorkflowTemplate
from tests.fixtures.fake_comfy import FakeComfyServer
from tests.production.test_preflight import h3_object_info


WORKFLOW = Path("backend/production/workflows/h3/reference.json")


@pytest.fixture
def segment_request(tmp_path: Path) -> H3SegmentRequest:
    pictures = tuple(tmp_path / f"picture-{index}.png" for index in range(1, 4))
    for picture in pictures:
        picture.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    package = H3ReferencePackage(
        shot_id="shot-1",
        prompt_version="v1",
        prompt_text="The hero looks toward the doorway.",
        negative_prompt="",
        base_seed=42,
        effective_seed=42,
        duration_seconds=5,
        legal_frame_count=124,
        width=864,
        height=480,
        aspect_ratio=AspectRatio.LANDSCAPE,
        picture_asset_version_ids=["asset-1", "asset-2", "asset-3"],
        video_reference_asset_version_ids=[],
        audio_reference_asset_version_ids=[],
        workflow_version="h3-ref2va-v1",
        model_registry_ids={
            "diffusion_model": "h3-unet.safetensors",
            "text_encoder": "h3-text.safetensors",
            "video_vae": "h3-video-vae.safetensors",
            "audio_vae": "h3-audio-vae.safetensors",
        },
    )
    return H3SegmentRequest(
        package=package,
        picture_paths=pictures,
        output_video=tmp_path / "segment.mp4",
        output_tail=tmp_path / "segment-tail.png",
    )


@pytest.fixture
def fake_comfy():
    with FakeComfyServer() as server:
        yield server


@pytest.fixture
def fake_comfy_no_output():
    with FakeComfyServer(no_output=True) as server:
        yield server


def approved_asset(asset_id: str, path: Path, state: str = "approved", digest: str = "") -> AssetVersion:
    """Build a resolved asset whose stored digest binds its approved file content."""
    return AssetVersion(
        id=asset_id,
        project_id="project-1",
        run_id="run-1",
        shot_id="shot-1",
        kind="image",
        state=state,
        path=path,
        sha256=digest or sha256(path.read_bytes()).hexdigest(),
    )


def provider(
    fake_comfy: FakeComfyServer,
    asset_store: AtomicAssetStore | None = None,
    asset_resolver: Callable[[str], AssetVersion | None] | None = None,
) -> H3Ref2VASegmentProvider:
    """Create the provider against the HTTP fake, retaining real adapter behavior."""
    return H3Ref2VASegmentProvider(
        adapter=ComfyUIAdapter(
            base_url=fake_comfy.base_url,
            poll_interval=0.01,
            timeout_seconds=1,
        ),
        template=WorkflowTemplate.load(WORKFLOW),
        asset_store=asset_store or AtomicAssetStore(),
        asset_resolver=asset_resolver,
    )


def resolver_for(
    request: H3SegmentRequest,
    overrides: dict[str, AssetVersion | None] | None = None,
) -> Callable[[str], AssetVersion | None]:
    """Provide the registered records that the provider, not the caller, treats as authoritative."""
    registered = {
        asset_id: approved_asset(asset_id, path)
        for asset_id, path in zip(
            request.package.picture_asset_version_ids,
            request.picture_paths,
            strict=True,
        )
    }
    registered.update(overrides or {})
    return registered.get


@pytest.mark.asyncio
async def test_provider_uploads_pictures_and_returns_video_audio_tail(
    fake_comfy: FakeComfyServer, segment_request: H3SegmentRequest
):
    """Catch a provider that skips uploads, the ref-image links, or media evidence."""
    result = await provider(fake_comfy, asset_resolver=resolver_for(segment_request)).generate(segment_request)

    assert result.prompt_id == fake_comfy.last_prompt_id
    assert result.video_path.is_file()
    assert result.tail_frame_path.is_file()
    assert result.audio_present is True
    assert result.comfy_output.media_kind == "videos"
    assert result.metadata["media"]["video"]["codec"]
    assert result.metadata["media"]["audio"]["codec"]
    assert fake_comfy.uploaded_filenames == [
        "picture-1.png",
        "picture-2.png",
        "picture-3.png",
    ]
    assert fake_comfy.history_requests >= 2
    assert fake_comfy.last_prompt["15"]["inputs"]["ref_images"] == [
        ["7", 0],
        ["8", 0],
        ["9", 0],
    ]


@pytest.mark.asyncio
async def test_authoritative_preflight_rebinds_models_and_rejects_stale_payload_before_upload(
    fake_comfy: FakeComfyServer, segment_request: H3SegmentRequest,
):
    """The queued payload never selects a local model and drift stops before upload/prompt."""
    instance = provider(fake_comfy, asset_resolver=resolver_for(segment_request))
    instance.object_info_fetcher = h3_object_info

    with pytest.raises(ProductionError) as error:
        await instance.generate(segment_request)

    assert error.value.code is ProductionErrorCode.COMFY_WORKFLOW_INVALID
    assert fake_comfy.uploaded_filenames == []
    assert fake_comfy.last_prompt == {}


@pytest.mark.asyncio
async def test_authoritative_preflight_replaces_empty_payload_model_ids_before_prompt(
    fake_comfy: FakeComfyServer, segment_request: H3SegmentRequest,
):
    instance = provider(fake_comfy, asset_resolver=resolver_for(segment_request))
    instance.object_info_fetcher = h3_object_info
    request = H3SegmentRequest(
        package=segment_request.package.model_copy(update={"model_registry_ids": {}}),
        picture_paths=segment_request.picture_paths,
        output_video=segment_request.output_video,
        output_tail=segment_request.output_tail,
    )

    await instance.generate(request)

    assert fake_comfy.last_prompt["1"]["inputs"]["clip_name"] == "Qwen/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
    assert fake_comfy.last_prompt["4"]["inputs"]["unet_name"] == "MiniMax-H3/minimax_h3_ref2va_pruned_int8_convrot.safetensors"


def test_decoded_quality_gate_rejects_black_frozen_or_silent_media(monkeypatch, tmp_path):
    """A syntactically valid container must still contain motion, light, and audible audio."""
    def completed(command, **kwargs):
        if "volumedetect" in command:
            return subprocess.CompletedProcess(command, 0, "", "max_volume: -91.0 dB")
        return subprocess.CompletedProcess(command, 0, "", "black_start:0 black_end:5\nfreeze_start: 0")
    monkeypatch.setattr("backend.novel_video.h3_provider.subprocess.run", completed)

    with pytest.raises(ProductionError) as error:
        H3Ref2VASegmentProvider._validate_decoded_quality(tmp_path / "candidate.mp4")

    assert error.value.code is ProductionErrorCode.MEDIA_VALIDATION_FAILED
    assert error.value.details["black"] is True
    assert error.value.details["frozen"] is True


def test_committed_manifest_is_adopted_without_a_new_prompt(fake_comfy, segment_request):
    """A crash after paired publication is recoverable as DB lineage-only work."""
    instance = provider(fake_comfy, asset_resolver=resolver_for(segment_request))
    segment_request.output_video.write_bytes(fake_comfy.video_payload)
    segment_request.output_tail.write_bytes(b"tail")
    manifest = instance._manifest_path(segment_request)
    instance._write_manifest(manifest, {
        "token": "publish-token", "prompt_id": "prompt-1", "state": "committed",
        "binding": instance._manifest_binding(segment_request),
        "destinations": {"video": str(segment_request.output_video.resolve()), "tail": str(segment_request.output_tail.resolve())},
        "digests": {"video": instance._file_digest(segment_request.output_video), "tail": instance._file_digest(segment_request.output_tail)},
    })

    result = instance._adopt_committed_publication(segment_request, manifest)

    assert result is not None
    assert result.prompt_id == "prompt-1"
    assert result.metadata["recovery"]["adopted_committed_manifest"] is True


@pytest.mark.asyncio
async def test_completed_history_without_video_is_failure(
    fake_comfy_no_output: FakeComfyServer, segment_request: H3SegmentRequest
):
    """Catch terminal ComfyUI history that is incorrectly treated as a media result."""
    with pytest.raises(ProductionError) as error:
        await provider(
            fake_comfy_no_output,
            asset_resolver=resolver_for(segment_request),
        ).generate(segment_request)

    assert error.value.code is ProductionErrorCode.COMFY_NO_OUTPUT


@pytest.mark.asyncio
async def test_provider_rejects_media_that_does_not_match_the_approved_package_before_publish(
    fake_comfy: FakeComfyServer, segment_request: H3SegmentRequest
):
    """Catch a mismatched Comfy video being published despite its package contract."""
    mismatched = segment_request.package.model_copy(update={"width": 832})
    request = H3SegmentRequest(mismatched, segment_request.picture_paths, segment_request.output_video, segment_request.output_tail)

    with pytest.raises(ProductionError) as error:
        await provider(fake_comfy, asset_resolver=resolver_for(segment_request)).generate(request)

    assert error.value.code is ProductionErrorCode.MEDIA_VALIDATION_FAILED
    assert not request.output_video.exists()
    assert not request.output_tail.exists()


@pytest.mark.asyncio
async def test_provider_rejects_unbound_video_or_audio_references_before_submission(
    fake_comfy: FakeComfyServer, segment_request: H3SegmentRequest
):
    """Catch declared reference assets becoming dead, silently ignored workflow inputs."""
    package = segment_request.package.model_copy(update={"video_reference_asset_version_ids": ["video-ref"]})
    request = H3SegmentRequest(package, segment_request.picture_paths, segment_request.output_video, segment_request.output_tail)

    with pytest.raises(ProductionError) as error:
        await provider(fake_comfy, asset_resolver=resolver_for(segment_request)).generate(request)

    assert error.value.code is ProductionErrorCode.MEDIA_VALIDATION_FAILED
    assert fake_comfy.uploaded_filenames == []


@pytest.mark.asyncio
async def test_provider_requires_picture_paths_to_match_package_assets(
    fake_comfy: FakeComfyServer, segment_request: H3SegmentRequest
):
    """Catch accidental upload of a picture not represented by the approved package."""
    mismatched = H3SegmentRequest(
        package=segment_request.package,
        picture_paths=segment_request.picture_paths[:2],
        output_video=segment_request.output_video,
        output_tail=segment_request.output_tail,
    )

    with pytest.raises(ProductionError) as error:
        await provider(fake_comfy, asset_resolver=resolver_for(segment_request)).generate(mismatched)

    assert error.value.code is ProductionErrorCode.MEDIA_VALIDATION_FAILED


@pytest.mark.asyncio
async def test_provider_never_overwrites_finalized_video(
    fake_comfy: FakeComfyServer, segment_request: H3SegmentRequest
):
    """Catch publishing that replaces a previously finalized segment."""
    segment_request.output_video.write_bytes(b"finalized-video")

    with pytest.raises(FileExistsError):
        await provider(fake_comfy, asset_resolver=resolver_for(segment_request)).generate(segment_request)

    assert segment_request.output_video.read_bytes() == b"finalized-video"


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", ["wrong_id", "wrong_path", "wrong_hash"])
async def test_provider_rejects_same_count_picture_substitution(
    fake_comfy: FakeComfyServer,
    segment_request: H3SegmentRequest,
    tmp_path: Path,
    replacement: str,
):
    """Catch same-count inputs whose resolved asset identity or digest is not approved."""
    if replacement == "wrong_id":
        package = segment_request.package.model_copy(
            update={"picture_asset_version_ids": ["unapproved-id", "asset-2", "asset-3"]}
        )
        paths = segment_request.picture_paths
        resolver = resolver_for(segment_request)
    else:
        replacement_path = tmp_path / f"{replacement}.png"
        replacement_path.write_bytes(b"\x89PNG\r\n\x1a\nsubstituted")
        package = segment_request.package
        paths = (replacement_path, *segment_request.picture_paths[1:])
        resolver = resolver_for(
            segment_request,
            (
                {"asset-1": approved_asset("asset-1", segment_request.picture_paths[0], digest="0" * 64)}
                if replacement == "wrong_hash"
                else None
            ),
        )
    substituted = H3SegmentRequest(
        package=package,
        picture_paths=paths,
        output_video=segment_request.output_video,
        output_tail=segment_request.output_tail,
    )

    with pytest.raises(ProductionError) as error:
        await provider(fake_comfy, asset_resolver=resolver).generate(substituted)

    assert error.value.code is ProductionErrorCode.MEDIA_VALIDATION_FAILED
    assert fake_comfy.uploaded_filenames == []


@pytest.mark.asyncio
async def test_provider_rejects_non_approved_picture_asset(
    fake_comfy: FakeComfyServer, segment_request: H3SegmentRequest
):
    """Catch a resolved asset that has not passed the candidate-to-approved gate."""
    unapproved = H3SegmentRequest(
        package=segment_request.package,
        picture_paths=segment_request.picture_paths,
        output_video=segment_request.output_video,
        output_tail=segment_request.output_tail,
    )

    with pytest.raises(ProductionError) as error:
        await provider(
            fake_comfy,
            asset_resolver=resolver_for(
                segment_request,
                {"asset-2": approved_asset("asset-2", segment_request.picture_paths[1], state="candidate")},
            ),
        ).generate(unapproved)

    assert error.value.code is ProductionErrorCode.MEDIA_VALIDATION_FAILED


class CrashAfterVideoStore:
    """Raise after the video rename to simulate process interruption before tail publish."""

    def __init__(self):
        self.calls = 0
        self.delegate = AtomicAssetStore()

    def publish(self, temp_path: Path, final_path: Path) -> tuple[Path, str]:
        self.calls += 1
        if self.calls == 2:
            raise KeyboardInterrupt("simulated crash after video publish")
        return self.delegate.publish(temp_path, final_path)


class ConcurrentReplacementStore:
    """Simulate an external writer replacing the first final file before tail failure."""

    def __init__(self):
        self.calls = 0
        self.delegate = AtomicAssetStore()
        self.video_path: Path | None = None

    def publish(self, temp_path: Path, final_path: Path) -> tuple[Path, str]:
        self.calls += 1
        if self.calls == 1:
            self.video_path = final_path
            return self.delegate.publish(temp_path, final_path)
        assert self.video_path is not None
        self.video_path.write_bytes(b"concurrent-writer")
        raise RuntimeError("tail publish failed")


class CrashBeforeVideoStore:
    """Raise after the durable prepare record but before any final output is published."""

    def publish(self, temp_path: Path, final_path: Path) -> tuple[Path, str]:
        raise KeyboardInterrupt("simulated crash before first publish")


class FailBeforeVideoStore:
    """Fail the first publish before rename, leaving an auditable non-committed manifest only."""

    def publish(self, temp_path: Path, final_path: Path) -> tuple[Path, str]:
        raise RuntimeError("simulated first publish failure")


class ReplacingUploadAdapter(ComfyUIAdapter):
    """Replace a source file immediately before upload to prove the provider uploads captured bytes."""

    def __init__(self, source_path: Path, replacement: bytes, **kwargs):
        super().__init__(**kwargs)
        self.source_path = source_path
        self.replacement = replacement
        self.replaced = False

    async def upload_image_bytes(
        self,
        payload: bytes,
        filename: str,
        subfolder: str = "novel_video",
    ):
        if not self.replaced:
            self.source_path.write_bytes(self.replacement)
            self.replaced = True
        return await super().upload_image_bytes(payload, filename, subfolder)


@pytest.mark.asyncio
async def test_provider_blocks_crash_after_video_before_tail_publish(
    fake_comfy: FakeComfyServer, segment_request: H3SegmentRequest
):
    """Catch recovery that would destructively remove a crash-left partial final output."""
    with pytest.raises(KeyboardInterrupt):
        await provider(
            fake_comfy,
            CrashAfterVideoStore(),
            resolver_for(segment_request),
        ).generate(segment_request)

    assert segment_request.output_video.is_file()
    assert not segment_request.output_tail.exists()

    with pytest.raises(ProductionError, match="Incomplete H3 publication"):
        await provider(
            fake_comfy,
            asset_resolver=resolver_for(segment_request),
        ).generate(segment_request)

    assert segment_request.output_video.is_file()
    assert not segment_request.output_tail.exists()


@pytest.mark.asyncio
async def test_provider_never_deletes_competing_writer_after_tail_publish_failure(
    fake_comfy: FakeComfyServer, segment_request: H3SegmentRequest
):
    """Catch rollback that deletes a destination no longer owned by this generation."""
    with pytest.raises(RuntimeError, match="tail publish failed"):
        await provider(
            fake_comfy,
            ConcurrentReplacementStore(),
            resolver_for(segment_request),
        ).generate(segment_request)

    assert segment_request.output_video.read_bytes() == b"concurrent-writer"


@pytest.mark.asyncio
async def test_provider_uploads_the_verified_bytes_when_source_changes_before_upload(
    fake_comfy: FakeComfyServer, segment_request: H3SegmentRequest
):
    """Catch a second source-path open that can upload bytes different from the approved digest."""
    original = segment_request.picture_paths[0].read_bytes()
    adapter = ReplacingUploadAdapter(
        source_path=segment_request.picture_paths[0],
        replacement=b"\x89PNG\r\n\x1a\nraced-replacement",
        base_url=fake_comfy.base_url,
        poll_interval=0.01,
        timeout_seconds=1,
    )
    h3_provider = H3Ref2VASegmentProvider(
        adapter=adapter,
        template=WorkflowTemplate.load(WORKFLOW),
        asset_resolver=resolver_for(segment_request),
    )

    await h3_provider.generate(segment_request)

    assert fake_comfy.uploaded_payloads[0] == original
    assert segment_request.picture_paths[0].read_bytes() != original


@pytest.mark.asyncio
async def test_formal_resume_rejects_altered_canonical_request_before_history_wait(fake_comfy, segment_request):
    h3_provider = provider(fake_comfy, asset_resolver=resolver_for(segment_request))
    h3_provider.task_binding = {"task_id": "task-1", "run_id": "run-1", "shot_id": segment_request.package.shot_id, "attempt_id": "task-1:1"}
    checkpoint = {**h3_provider._manifest_binding(segment_request), "prompt_id": "prompt-1"}
    altered = H3SegmentRequest(
        segment_request.package.model_copy(update={"effective_seed": segment_request.package.effective_seed + 1}),
        segment_request.picture_paths, segment_request.output_video, segment_request.output_tail,
    )

    with pytest.raises(ProductionError, match="checkpoint binding mismatch"):
        await h3_provider.resume(altered, "prompt-1", checkpoint)
    assert fake_comfy.history_requests == 0


@pytest.mark.asyncio
async def test_provider_supersedes_prepared_manifest_without_final_outputs(
    fake_comfy: FakeComfyServer, segment_request: H3SegmentRequest
):
    """Catch an empty prepared transaction that permanently blocks a safe new generation."""
    with pytest.raises(KeyboardInterrupt):
        await provider(
            fake_comfy,
            CrashBeforeVideoStore(),
            resolver_for(segment_request),
        ).generate(segment_request)

    result = await provider(
        fake_comfy,
        asset_resolver=resolver_for(segment_request),
    ).generate(segment_request)

    assert result.video_path.is_file()
    assert result.tail_frame_path.is_file()
    assert list(segment_request.output_video.parent.glob("*.h3.transaction.json.superseded.*"))


@pytest.mark.asyncio
async def test_provider_retries_failed_first_publish_when_no_final_outputs_exist(
    fake_comfy: FakeComfyServer, segment_request: H3SegmentRequest
):
    """Catch recovery that blocks a retry even though no immutable final output was ever created."""
    with pytest.raises(RuntimeError, match="simulated first publish failure"):
        await provider(
            fake_comfy,
            FailBeforeVideoStore(),
            resolver_for(segment_request),
        ).generate(segment_request)

    result = await provider(
        fake_comfy,
        asset_resolver=resolver_for(segment_request),
    ).generate(segment_request)

    assert result.video_path.is_file()
    assert result.tail_frame_path.is_file()
    assert list(segment_request.output_video.parent.glob("*.h3.transaction.json.superseded.*"))


@pytest.mark.asyncio
async def test_provider_fails_closed_without_authoritative_asset_resolver(
    fake_comfy: FakeComfyServer, segment_request: H3SegmentRequest
):
    """Catch caller-created approval records being accepted without a provider-bound authority."""
    with pytest.raises(ProductionError) as error:
        await provider(fake_comfy).generate(segment_request)

    assert error.value.code is ProductionErrorCode.MEDIA_VALIDATION_FAILED


def test_request_preserves_brief_compatible_picture_paths_constructor(
    segment_request: H3SegmentRequest,
):
    """Catch a public request contract that drops the brief's picture_paths constructor field."""
    assert segment_request.picture_paths[0].name == "picture-1.png"


@pytest.mark.asyncio
async def test_provider_rejects_normalized_equivalent_output_paths(
    fake_comfy: FakeComfyServer, segment_request: H3SegmentRequest, tmp_path: Path
):
    """Catch aliases that bypass raw-path equality checks and target the same finalized file."""
    aliased = H3SegmentRequest(
        package=segment_request.package,
        picture_paths=segment_request.picture_paths,
        output_video=tmp_path / "alias" / ".." / "same.mp4",
        output_tail=tmp_path / "same.mp4",
    )

    with pytest.raises(ProductionError) as error:
        await provider(fake_comfy, asset_resolver=resolver_for(segment_request)).generate(aliased)

    assert error.value.code is ProductionErrorCode.MEDIA_VALIDATION_FAILED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal_entry",
    [
        {"outputs": [], "status": {"status_str": "success", "completed": True}},
        {"outputs": {}, "status": {"status_str": "cancelled", "completed": True}},
        {"outputs": {}, "status": {"status_str": "success", "completed": False}},
    ],
)
async def test_adapter_rejects_invalid_or_unsuccessful_terminal_history(
    terminal_entry: dict,
):
    """Catch terminal history records that must not be retried or accepted as success."""
    with FakeComfyServer(terminal_entry=terminal_entry) as fake:
        adapter = ComfyUIAdapter(
            base_url=fake.base_url,
            poll_interval=0.01,
            timeout_seconds=1,
        )
        with pytest.raises(ProductionError) as error:
            await adapter.submit_and_wait({"1": {"class_type": "SaveImage"}})

    assert error.value.code is ProductionErrorCode.COMFY_EXECUTION_FAILED
