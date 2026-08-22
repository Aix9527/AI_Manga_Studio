from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.novel_video.repository import NovelVideoRepository


UNIFIED_WORKFLOW_VERSIONS = frozenset({"h3_unified", "h3-unified", "unified"})


def build_formal_novel_video_router_factory(novel_video_repo: NovelVideoRepository):
    """Build the persisted formal H3 provider lazily for one queued segment."""

    def factory(*, allow_wan_fallback: bool, project: Any, payload: dict):
        from backend.novel_video.h3_provider import H3Ref2VASegmentProvider
        from backend.novel_video.video_router import NovelVideoRouter
        from backend.production.comfy_adapter import ComfyUIAdapter
        from backend.production.comfy_video import WanVideoProvider
        from backend.production.workflow_registry import select_wan_video_workflow
        from backend.production.workflow_templates import WorkflowTemplate

        workflows = Path(__file__).resolve().parents[1] / "production" / "workflows"
        adapter = ComfyUIAdapter(base_url="http://127.0.0.1:8188")
        package = payload.get("package") if isinstance(payload, dict) else None
        workflow_version = str(package.get("workflow_version", "")) if isinstance(package, dict) else ""
        asset_resolver = lambda asset_id: _scoped_asset(
            novel_video_repo,
            asset_id,
            project.id,
            str(payload["run_id"]),
        )

        if workflow_version in UNIFIED_WORKFLOW_VERSIONS:
            from backend.video.h3_unified.comfy_media import H3ComfyMediaAdapter
            from backend.video.h3_unified.formal_provider import H3UnifiedFormalSegmentProvider

            h3 = H3UnifiedFormalSegmentProvider(
                adapter=H3ComfyMediaAdapter(base=adapter),
                asset_resolver=asset_resolver,
            )
        else:
            h3 = H3Ref2VASegmentProvider(
                adapter=adapter,
                template=WorkflowTemplate.load(workflows / "h3" / "reference.json"),
                asset_resolver=asset_resolver,
                object_info_fetcher=adapter.get_object_info,
            )

        wan = None
        if allow_wan_fallback:
            spec = select_wan_video_workflow(has_end_frame=False)
            wan = WanVideoProvider(
                adapter=adapter,
                template=WorkflowTemplate.load(workflows / spec.path.name),
            )
        return NovelVideoRouter(
            h3=h3,
            wan=wan,
            allow_wan_fallback=allow_wan_fallback,
        )

    return factory


def _scoped_asset(
    repository: NovelVideoRepository,
    asset_id: str,
    project_id: str,
    run_id: str,
):
    """Resolve only an approved project asset; continuity compiler restricts tails."""

    asset = repository.get_asset(asset_id)
    return asset if asset and asset.project_id == project_id and asset.state == "approved" else None
