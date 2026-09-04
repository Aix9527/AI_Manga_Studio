from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from backend.orchestration.schemas import JobDetail
from backend.workspace.models import (
    DirectorSettings,
    ProjectAsset,
    StageAutomation,
    StageKey,
    WorkspaceSnapshot,
)
from backend.workspace.service import (
    AssetNotFound,
    AssetNotReviewable,
    JobServiceUnavailable,
    UnsupportedAssetMedia,
    WorkspaceService,
)


router = APIRouter(prefix="/api/workspace", tags=["workspace"])


def _service(request: Request) -> WorkspaceService:
    return request.app.state.workspace_service


@router.get("/{project_id}", response_model=WorkspaceSnapshot)
async def get_workspace(project_id: str, request: Request) -> WorkspaceSnapshot:
    return _service(request).get_snapshot(project_id)


@router.put("/{project_id}/automation/{stage_key}", response_model=StageAutomation)
async def update_automation(
    project_id: str,
    stage_key: StageKey,
    value: StageAutomation,
    request: Request,
) -> StageAutomation:
    if value.stage_key != stage_key:
        raise HTTPException(status_code=422, detail="阶段标识不一致")
    return _service(request).update_automation(project_id, value)


@router.get("/{project_id}/assets", response_model=list[ProjectAsset])
async def list_project_assets(
    project_id: str,
    request: Request,
    kind: str | None = None,
    stage_key: str | None = None,
    scene_id: str | None = None,
    shot_id: str | None = None,
    quality_status: str | None = None,
    active: bool | None = Query(None),
) -> list[ProjectAsset]:
    return _service(request).list_assets(
        project_id,
        kind=kind,
        stage_key=stage_key,
        scene_id=scene_id,
        shot_id=shot_id,
        quality_status=quality_status,
        active=active,
    )


@router.put("/{project_id}/assets/{asset_id}/director", response_model=ProjectAsset)
async def update_asset_director_settings(
    project_id: str,
    asset_id: int,
    value: DirectorSettings,
    request: Request,
) -> ProjectAsset:
    try:
        return _service(request).update_director_settings(project_id, asset_id, value)
    except AssetNotFound as error:
        raise HTTPException(status_code=404, detail="素材不存在") from error


@router.get("/{project_id}/assets/{asset_id}/media", response_class=FileResponse)
async def get_project_asset_media(project_id: str, asset_id: int, request: Request) -> FileResponse:
    try:
        media = _service(request).get_asset_media(project_id, asset_id)
    except UnsupportedAssetMedia as error:
        raise HTTPException(status_code=415, detail="不支持的素材类型") from error
    if media is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    path, media_type = media
    return FileResponse(path, media_type=media_type, content_disposition_type="inline")


@router.post("/{project_id}/assets/{asset_id}/regenerate", response_model=JobDetail)
async def regenerate_project_asset(project_id: str, asset_id: int, request: Request) -> JobDetail:
    try:
        return _service(request).regenerate_asset(project_id, asset_id)
    except AssetNotFound as error:
        raise HTTPException(status_code=404, detail="素材不存在") from error
    except AssetNotReviewable as error:
        raise HTTPException(status_code=409, detail="该素材版本当前不处于待审核状态") from error
    except JobServiceUnavailable as error:
        raise HTTPException(status_code=503, detail="任务服务尚未就绪") from error
