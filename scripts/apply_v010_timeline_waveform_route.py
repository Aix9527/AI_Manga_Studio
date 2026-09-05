from pathlib import Path

path = Path("backend/timeline/routes.py")
text = path.read_text(encoding="utf-8")
if "WaveformEnvelope" not in text:
    text = text.replace(
        "    TimelineSummary,\n)",
        "    TimelineSummary,\n    WaveformEnvelope,\n)",
        1,
    )
if "from backend.timeline.waveform import WaveformService" not in text:
    text = text.replace(
        "from backend.timeline.service import (",
        "from backend.timeline.waveform import WaveformService\nfrom backend.timeline.service import (",
        1,
    )
if "get_timeline_artifact_waveform" not in text:
    text += '''\n\n@router.get("/api/timelines/{timeline_id}/artifacts/{artifact_id}/waveform", response_model=WaveformEnvelope)
async def get_timeline_artifact_waveform(
    timeline_id: str,
    artifact_id: int,
    request: Request,
    bins: int = 512,
) -> WaveformEnvelope:
    service = _service(request)
    timeline = service.repo.get_timeline(timeline_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail={"code": "TIMELINE_NOT_FOUND", "message": "Timeline not found"})
    waveform = WaveformService(
        service.repo.db,
        projects_root=service.repo.projects_root,
    )
    try:
        return waveform.get_or_build(str(timeline["project_id"]), artifact_id, bins=bins)
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"code": "TIMELINE_WAVEFORM_FAILED", "message": str(error)}) from error
'''
path.write_text(text, encoding="utf-8")
