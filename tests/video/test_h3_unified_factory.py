from __future__ import annotations

from types import SimpleNamespace

from backend.novel_video.provider_factory import build_formal_novel_video_router_factory
from backend.novel_video.h3_provider import H3Ref2VASegmentProvider
from backend.video.h3_unified.formal_provider import H3UnifiedFormalSegmentProvider


class FakeNovelVideoRepository:
    def get_asset(self, asset_id: str):
        return None


def test_formal_router_factory_selects_unified_provider_from_persisted_workflow_version() -> None:
    factory = build_formal_novel_video_router_factory(FakeNovelVideoRepository())
    project = SimpleNamespace(id="project-1", allow_wan_fallback=False)

    router = factory(
        allow_wan_fallback=False,
        project=project,
        payload={
            "run_id": "run-1",
            "package": {"workflow_version": "h3_unified"},
        },
    )

    assert isinstance(router.h3, H3UnifiedFormalSegmentProvider)
    assert router.allow_wan_fallback is False


def test_formal_router_factory_preserves_existing_ref2va_provider_for_legacy_workflow() -> None:
    factory = build_formal_novel_video_router_factory(FakeNovelVideoRepository())
    project = SimpleNamespace(id="project-1", allow_wan_fallback=False)

    router = factory(
        allow_wan_fallback=False,
        project=project,
        payload={
            "run_id": "run-1",
            "package": {"workflow_version": "h3_ref2va_v1"},
        },
    )

    assert isinstance(router.h3, H3Ref2VASegmentProvider)
    assert router.allow_wan_fallback is False
