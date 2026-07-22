from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from pydantic import BaseModel, Field

from backend.orchestration.repository import JobConflictError, JobNotFoundError
from backend.orchestration.schemas import JobCreate


router = APIRouter(prefix='/api/pipeline', tags=['Pipeline Compatibility'])
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
NOVELS_DIR = PROJECT_ROOT / 'novels'
NOVELS_DIR.mkdir(parents=True, exist_ok=True)


class PipelineRunRequest(BaseModel):
    novel_path: str
    style: Optional[str] = None
    chapter: Optional[int] = None
    max_shots: int = Field(default=1, ge=1, le=6)
    tts_enabled: bool = True
    subtitles_enabled: bool = True
    bgm_enabled: bool = False


class NovelListResponse(BaseModel):
    novels: list
    total: int


def _service(request: Request):
    return request.app.state.job_service


def _safe_project_id(path: Path) -> str:
    value = re.sub(r'[<>:\x22/\\|?*\x00-\x1f]', '_', path.stem).strip(' .')
    return (value or f'legacy-{uuid.uuid4().hex[:8]}')[:128]


def _command(body: PipelineRunRequest, idempotency_key: str) -> JobCreate:
    novel_path = Path(body.novel_path).resolve()
    if not novel_path.is_file():
        raise HTTPException(status_code=404, detail=f'Novel not found: {body.novel_path}')
    return JobCreate(
        project_id=_safe_project_id(novel_path),
        input_path=str(novel_path),
        input_type='novel',
        mode='automatic',
        shot_duration=5,
        width=1080,
        height=1920,
        fps=24,
        options={
            'style': body.style or 'realistic',
            'chapter': body.chapter,
            'max_shots': body.max_shots,
            'tts_enabled': body.tts_enabled,
            'subtitles_enabled': body.subtitles_enabled,
            'bgm_enabled': body.bgm_enabled,
        },
        idempotency_key=idempotency_key,
    )


def _legacy_view(job: dict) -> dict:
    settings = job.get('settings', {})
    input_path = settings.get('input_path', '')
    return {
        'job_id': job['id'],
        'novel': Path(input_path).name if input_path else '',
        'status': job['status'],
        'progress': job['progress'],
        'message': job['message'],
        'started_at': job['created_at'],
        'finished_at': job.get('finished_at'),
        'output_dir': '',
        'final_video': job['final_video'],
        'stage_list': job['steps'],
    }


@router.post('/run')
def run_pipeline(
    body: PipelineRunRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
):
    key = idempotency_key or f'legacy-{uuid.uuid4()}'
    return _legacy_view(_service(request).create(_command(body, key)))


@router.post('/upload')
async def upload_and_run(
    request: Request,
    file: UploadFile = File(...),
    style: str | None = Form(default=None),
    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
):
    safe_name = Path(file.filename or '').name
    if not safe_name.lower().endswith('.txt'):
        raise HTTPException(status_code=400, detail='Only .txt files accepted')
    novel_path = (NOVELS_DIR / safe_name).resolve()
    if NOVELS_DIR.resolve() not in novel_path.parents:
        raise HTTPException(status_code=400, detail='Unsafe file name')
    novel_path.write_bytes(await file.read())
    body = PipelineRunRequest(novel_path=str(novel_path), style=style)
    key = idempotency_key or f'legacy-upload-{uuid.uuid4()}'
    return _legacy_view(_service(request).create(_command(body, key)))


@router.get('/status/{job_id}')
def get_status(job_id: str, request: Request):
    job = _service(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail='Job not found')
    return _legacy_view(job)


@router.get('/novels')
def list_novels():
    candidates = list(NOVELS_DIR.glob('*.txt'))
    candidates.extend(PROJECT_ROOT.glob('novel*.txt'))
    novels = [
        {
            'name': item.name,
            'path': str(item.resolve()),
            'size': item.stat().st_size,
            'modified': datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
        }
        for item in sorted(set(candidates))
        if item.is_file()
    ]
    return {'total': len(novels), 'novels': novels}


@router.delete('/jobs/{job_id}')
def cancel_job(
    job_id: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
):
    try:
        job = _service(request).cancel(
            job_id, idempotency_key or f'legacy-cancel-{uuid.uuid4()}'
        )
    except JobNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except JobConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _legacy_view(job)
