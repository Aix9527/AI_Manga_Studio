from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from backend.production.comfy_adapter import ProductionError, ProductionErrorCode
from backend.production.providers import MediaArtifact, VideoRequest


@dataclass
class RecordingProvider:
    outcomes: list[MediaArtifact | Exception]
    requests: list[VideoRequest] = field(default_factory=list)

    async def generate(self, request: VideoRequest) -> MediaArtifact:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def request() -> VideoRequest:
    return VideoRequest(
        image_path=Path("approved.png"), prompt="move forward", negative_prompt="", seed=42,
        width=1024, height=576, frames=124, fps=24, output_path=Path("segment.mp4"),
    )


@pytest.mark.asyncio
async def test_h3_failure_does_not_call_wan_when_disabled():
    """Catch a router that silently changes the approved engine without permission."""
    from backend.novel_video.video_router import NovelVideoRouter

    h3 = RecordingProvider([ProductionError(ProductionErrorCode.COMFY_EXECUTION_FAILED, "bad workflow")])
    wan = RecordingProvider([MediaArtifact(Path("wan.mp4"), "video")])

    with pytest.raises(ProductionError):
        await NovelVideoRouter(h3=h3, wan=wan, allow_wan_fallback=False).generate(request())

    assert wan.requests == []


@pytest.mark.asyncio
async def test_router_retries_connection_once_with_the_original_seed():
    """Catch retries that change the approved shot seed or retry indefinitely."""
    from backend.novel_video.video_router import NovelVideoRouter

    h3 = RecordingProvider([
        ProductionError(ProductionErrorCode.COMFY_CONNECTION_FAILED, "offline"),
        MediaArtifact(Path("h3.mp4"), "video"),
    ])
    result = await NovelVideoRouter(h3=h3, wan=None).generate(request())

    assert result.path == Path("h3.mp4")
    assert [item.seed for item in h3.requests] == [42, 42]
    assert [(item.width, item.height) for item in h3.requests] == [(1024, 576), (1024, 576)]


@pytest.mark.asyncio
async def test_timeout_after_accepted_prompt_reconciles_without_second_submit():
    """Transport retry after acceptance is a history resume, never a new `/prompt`."""
    from backend.novel_video.video_router import NovelVideoRouter

    class Provider:
        def __init__(self):
            self.submits = 0
            self.resumes = []
        async def generate(self, value):
            self.submits += 1
            raise ProductionError(ProductionErrorCode.COMFY_TIMEOUT, "history timeout", {"accepted_prompt_id": "prompt-1"})
        async def resume(self, value, prompt_id):
            self.resumes.append(prompt_id)
            return MediaArtifact(Path("reconciled.mp4"), "video")
    h3 = Provider()
    result = await NovelVideoRouter(h3=h3, wan=None).generate(request())
    assert result.path == Path("reconciled.mp4")
    assert h3.submits == 1
    assert h3.resumes == ["prompt-1"]


@pytest.mark.asyncio
async def test_second_transport_attempt_with_accepted_oom_reconciles_without_downgrade():
    """An accepted OOM is terminal history for that prompt, never permission for prompt two."""
    from backend.novel_video.video_router import NovelVideoRouter

    class Provider:
        def __init__(self):
            self.submits = 0
            self.resumes = []

        async def generate(self, value):
            self.submits += 1
            if self.submits == 1:
                raise ProductionError(ProductionErrorCode.COMFY_CONNECTION_FAILED, "before accept")
            raise ProductionError(ProductionErrorCode.COMFY_OOM, "accepted OOM", {"accepted_prompt_id": "accepted-oom"})

        async def resume(self, value, prompt_id, checkpoint=None):
            self.resumes.append(prompt_id)
            raise ProductionError(ProductionErrorCode.COMFY_OOM, "terminal OOM", {"accepted_prompt_id": prompt_id})

    h3 = Provider()
    with pytest.raises(ProductionError) as error:
        await NovelVideoRouter(h3=h3, wan=None).generate(request())

    assert error.value.code is ProductionErrorCode.COMFY_OOM
    assert h3.submits == 2
    assert h3.resumes == ["accepted-oom"]


@pytest.mark.asyncio
async def test_router_reduces_first_oom_by_25_percent_without_changing_aspect_or_seed():
    """Catch OOM recovery that uses the wrong area reduction, alignment, aspect, or seed."""
    from backend.novel_video.video_router import NovelVideoRouter

    h3 = RecordingProvider([
        ProductionError(ProductionErrorCode.COMFY_OOM, "out of memory"),
        MediaArtifact(Path("h3.mp4"), "video"),
    ])
    result = await NovelVideoRouter(h3=h3, wan=None).generate(request())

    assert [(item.width, item.height, item.seed) for item in h3.requests] == [
        (1024, 576, 42), (864, 480, 42),
    ]
    assert result.metadata["routing"]["original_size"] == {"width": 1024, "height": 576}
    assert result.metadata["routing"]["downgraded_size"] == {"width": 864, "height": 480}
    geometry = result.metadata["routing"]["geometry"]
    assert geometry["target_area"] == pytest.approx(1024 * 576 * 0.75)
    assert geometry["actual_area"] == 864 * 480
    assert geometry["actual_area"] <= geometry["target_area"]
    assert geometry["actual_reduction"] >= 0.25
    assert geometry["aspect_error"] < 0.02


@pytest.mark.asyncio
async def test_router_resizes_the_formal_h3_segment_package_without_changing_its_seed():
    """Catch routing that only works for legacy VideoRequest instead of the formal H3 package."""
    from backend.novel_video.h3_provider import H3SegmentRequest
    from backend.novel_video.models import AspectRatio, H3ReferencePackage
    from backend.novel_video.video_router import NovelVideoRouter

    package = H3ReferencePackage(
        shot_id="shot-1", prompt_version="v1", prompt_text="move forward", base_seed=42,
        effective_seed=42, duration_seconds=5, legal_frame_count=124, width=1024, height=576,
        aspect_ratio=AspectRatio.LANDSCAPE, video_reference_asset_version_ids=[],
        audio_reference_asset_version_ids=[], workflow_version="h3-ref2va-v1",
    )
    segment = H3SegmentRequest(
        package=package, picture_paths=(), output_video=Path("segment.mp4"),
        output_tail=Path("segment-tail.png"),
    )
    h3 = RecordingProvider([
        ProductionError(ProductionErrorCode.COMFY_OOM, "out of memory"),
        MediaArtifact(Path("h3.mp4"), "video"),
    ])

    await NovelVideoRouter(h3=h3, wan=None).generate(segment)

    assert [(item.package.width, item.package.height, item.package.effective_seed) for item in h3.requests] == [
        (1024, 576, 42), (864, 480, 42),
    ]


@pytest.mark.asyncio
async def test_router_retries_transport_then_performs_its_single_oom_downgrade():
    """Catch a retry state machine that skips OOM recovery after a transport retry."""
    from backend.novel_video.video_router import NovelVideoRouter

    h3 = RecordingProvider([
        ProductionError(ProductionErrorCode.COMFY_TIMEOUT, "timed out"),
        ProductionError(ProductionErrorCode.COMFY_OOM, "out of memory"),
        MediaArtifact(Path("h3.mp4"), "video"),
    ])
    wan = RecordingProvider([MediaArtifact(Path("wan.mp4"), "video")])

    result = await NovelVideoRouter(h3=h3, wan=wan, allow_wan_fallback=True).generate(request())

    assert result.path == Path("h3.mp4")
    assert [(item.width, item.height, item.seed) for item in h3.requests] == [
        (1024, 576, 42), (1024, 576, 42), (864, 480, 42),
    ]
    assert wan.requests == []


@pytest.mark.asyncio
async def test_router_blocks_subminimum_oom_recovery_without_wan_permission():
    """Catch a router that creates an unusable sub-0.3MP retry or falls back without consent."""
    from backend.novel_video.video_router import NovelVideoRouter

    blocked: list[dict] = []
    h3 = RecordingProvider([ProductionError(ProductionErrorCode.COMFY_OOM, "out of memory")])
    wan = RecordingProvider([MediaArtifact(Path("wan.mp4"), "video")])
    small = replace(request(), width=640, height=480)

    with pytest.raises(ProductionError) as error:
        await NovelVideoRouter(
            h3=h3, wan=wan, allow_wan_fallback=False, on_blocked=blocked.append,
        ).generate(small)

    assert error.value.code is ProductionErrorCode.COMFY_OOM
    assert blocked[0]["reason"] == "oom_downgrade_below_minimum"
    assert blocked[0]["original_size"] == {"width": 640, "height": 480}
    assert blocked[0]["downgraded_size"] == {"width": 544, "height": 384}
    assert blocked[0]["geometry"]["actual_area"] == 544 * 384
    assert wan.requests == []


@pytest.mark.asyncio
async def test_router_blocks_aligned_oom_geometry_outside_the_fixed_aspect_tolerance():
    """Catch a 32-aligned retry that preserves too little of the original portrait aspect."""
    from backend.novel_video.video_router import NovelVideoRouter

    blocked: list[dict] = []
    h3 = RecordingProvider([ProductionError(ProductionErrorCode.COMFY_OOM, "out of memory")])
    portrait = replace(request(), width=512, height=896)

    with pytest.raises(ProductionError) as error:
        await NovelVideoRouter(h3=h3, wan=None, on_blocked=blocked.append).generate(portrait)

    assert error.value.code is ProductionErrorCode.COMFY_OOM
    assert blocked[0]["reason"] == "oom_geometry_outside_tolerance"
    geometry = blocked[0]["geometry"]
    assert geometry["actual_area"] <= geometry["target_area"]
    assert geometry["aspect_error"] > geometry["bounds"]["max_aspect_error"]
    assert geometry["valid"] is False
    assert len(h3.requests) == 1


@pytest.mark.asyncio
async def test_router_logs_a_blocked_callback_failure_and_preserves_the_oom(caplog):
    """Catch optional evidence callbacks replacing the original terminal router failure."""
    from backend.novel_video.video_router import NovelVideoRouter

    def broken_callback(evidence):
        raise RuntimeError("evidence sink offline")

    h3 = RecordingProvider([ProductionError(ProductionErrorCode.COMFY_OOM, "out of memory")])
    with pytest.raises(ProductionError) as error:
        await NovelVideoRouter(h3=h3, wan=None, on_blocked=broken_callback).generate(
            replace(request(), width=640, height=480)
        )

    assert error.value.code is ProductionErrorCode.COMFY_OOM
    assert error.value.details["routing"]["original_size"] == {"width": 640, "height": 480}
    assert "Optional novel-video blocked callback failed" in caplog.text


@pytest.mark.asyncio
async def test_router_uses_wan_only_when_project_permission_is_enabled():
    """Catch a router that ignores the project's explicit Wan fallback setting."""
    from backend.novel_video.video_router import NovelVideoRouter

    h3 = RecordingProvider([ProductionError(ProductionErrorCode.COMFY_EXECUTION_FAILED, "bad workflow")])
    wan = RecordingProvider([MediaArtifact(Path("wan.mp4"), "video")])

    result = await NovelVideoRouter(h3=h3, wan=wan, allow_wan_fallback=True).generate(request())

    assert result.path == Path("wan.mp4")
    assert len(wan.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("approval_failure", ["unapproved reference", "wrong asset id", "wrong approved path", "SHA-256 mismatch"])
async def test_router_never_falls_back_after_authoritative_reference_validation_fails(approval_failure: str):
    """Catch Wan bypassing H3's authoritative reference approval/integrity boundary."""
    from backend.novel_video.video_router import NovelVideoRouter

    h3 = RecordingProvider([
        ProductionError(ProductionErrorCode.MEDIA_VALIDATION_FAILED, approval_failure)
    ])
    wan = RecordingProvider([MediaArtifact(Path("wan.mp4"), "video")])

    with pytest.raises(ProductionError) as error:
        await NovelVideoRouter(h3=h3, wan=wan, allow_wan_fallback=True).generate(request())

    assert error.value.code is ProductionErrorCode.MEDIA_VALIDATION_FAILED
    assert wan.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [ProductionErrorCode.COMFY_WORKFLOW_INVALID, ProductionErrorCode.COMFY_NO_OUTPUT])
async def test_router_never_falls_back_after_non_provider_configuration_failures(code):
    """Catch fallback broadening beyond the explicit provider-availability error allowlist."""
    from backend.novel_video.video_router import NovelVideoRouter

    h3 = RecordingProvider([ProductionError(code, "not a fallbackable provider failure")])
    wan = RecordingProvider([MediaArtifact(Path("wan.mp4"), "video")])

    with pytest.raises(ProductionError) as error:
        await NovelVideoRouter(h3=h3, wan=wan, allow_wan_fallback=True).generate(request())

    assert error.value.code is code
    assert wan.requests == []


@pytest.mark.asyncio
async def test_router_adapts_formal_h3_request_for_permitted_wan_fallback():
    """Catch a fallback that gives Wan an incompatible H3SegmentRequest object."""
    from backend.novel_video.h3_provider import H3SegmentRequest
    from backend.novel_video.models import AspectRatio, H3ReferencePackage
    from backend.novel_video.video_router import NovelVideoRouter

    package = H3ReferencePackage(
        shot_id="shot-1", prompt_version="v1", prompt_text="move forward", negative_prompt="blur",
        base_seed=42, effective_seed=77, duration_seconds=5, legal_frame_count=124,
        width=1024, height=576, aspect_ratio=AspectRatio.LANDSCAPE,
        video_reference_asset_version_ids=[], audio_reference_asset_version_ids=[],
        workflow_version="h3-ref2va-v1",
    )
    segment = H3SegmentRequest(
        package=package, picture_paths=(Path("approved-first.png"),),
        output_video=Path("segment.mp4"), output_tail=Path("segment-tail.png"),
    )
    h3 = RecordingProvider([ProductionError(ProductionErrorCode.COMFY_EXECUTION_FAILED, "bad workflow")])
    wan = RecordingProvider([MediaArtifact(Path("wan.mp4"), "video")])

    await NovelVideoRouter(h3=h3, wan=wan, allow_wan_fallback=True).generate(segment)

    wan_request = wan.requests[0]
    assert isinstance(wan_request, VideoRequest)
    assert (wan_request.image_path, wan_request.prompt, wan_request.negative_prompt) == (
        Path("approved-first.png"), "move forward", "blur",
    )
    assert (wan_request.width, wan_request.height, wan_request.seed, wan_request.output_path) == (
        1024, 576, 77, Path("segment.mp4"),
    )
