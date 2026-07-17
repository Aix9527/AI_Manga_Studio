"""Pipeline trigger route for V5 one-click novel-to-video generation."""
from __future__ import annotations

import uuid
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from loguru import logger
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/pipeline", tags=["Pipeline"])

PROJECT_ROOT = Path(__file__).parent.parent.parent
NOVELS_DIR = PROJECT_ROOT / "novels"
OUTPUT_DIR = PROJECT_ROOT / "output"
NOVELS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_jobs: Dict[str, Dict[str, Any]] = {}
_STAGE_ORDER = ["parse", "first_frame", "last_frame", "video", "export"]


class PipelineRunRequest(BaseModel):
    novel_path: str = Field(..., description="Path to novel .txt file")
    style: Optional[str] = Field(None, description="Art style")
    chapter: Optional[int] = Field(None, description="Specific chapter to process")
    max_shots: int = Field(1, ge=1, le=6, description="Max shots per chapter for this run")
    tts_enabled: bool = Field(True, description="Enable TTS voiceover")
    subtitles_enabled: bool = Field(True, description="Enable subtitles")
    bgm_enabled: bool = Field(False, description="Enable background music")


class PipelineStatusResponse(BaseModel):
    job_id: str
    novel: str
    status: str
    progress: float = 0.0
    message: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    output_dir: Optional[str] = None
    final_video: str = ""


class NovelListResponse(BaseModel):
    novels: list
    total: int


def _stage_list(job_id: str) -> list[dict[str, Any]]:
    stages = _jobs[job_id].setdefault("stages", {})
    defaults = {
        "parse": "解析小说与分镜",
        "first_frame": "生成首帧",
        "last_frame": "生成尾帧",
        "video": "首尾帧视频",
        "export": "输出成片文件",
    }
    return [
        stages.get(key, {"key": key, "label": defaults[key], "status": "pending", "detail": "", "output": ""})
        for key in _STAGE_ORDER
    ]


def _set_stage(job_id: str, key: str, label: str, status: str, detail: str = "", output: str = "") -> None:
    stages = _jobs[job_id].setdefault("stages", {})
    stages[key] = {"key": key, "label": label, "status": status, "detail": detail, "output": output}
    completed = sum(1 for item in _stage_list(job_id) if item["status"] in ("completed", "warning"))
    _jobs[job_id]["progress"] = min(0.98, completed / len(_STAGE_ORDER))


def _run_pipeline_thread(job_id: str, novel_path: str, style: Optional[str] = None, max_shots: int = 1) -> None:
    try:
        _jobs[job_id]["status"] = "running"
        _jobs[job_id]["message"] = "V5 主链路启动中..."

        from backend.scheduler.novel import NovelStage
        from backend.pipeline_v5 import PipelineV5

        novel_file = Path(novel_path)
        project_id = novel_file.stem

        _set_stage(job_id, "parse", "解析小说与分镜", "running", "正在拆分小说并写入镜头 JSON")
        parser = NovelStage(project_dir=str(OUTPUT_DIR))
        parse_result = parser.parse(str(novel_file), project_id=project_id, max_shots_per_chapter=max_shots)
        _set_stage(job_id, "parse", "解析小说与分镜", "completed", f"生成 {parse_result.total_shots} 个镜头")
        _set_stage(job_id, "first_frame", "生成首帧", "running", "提交首帧工作流")

        warnings: list[str] = []

        def on_shot(shot_result: Any) -> None:
            if shot_result.image_path:
                _set_stage(job_id, "first_frame", "生成首帧", "completed", "首帧已生成", shot_result.image_path)
                _set_stage(job_id, "last_frame", "生成尾帧", "running", "根据动作终态生成尾帧")
            if shot_result.last_frame_path:
                _set_stage(job_id, "last_frame", "生成尾帧", "completed", "尾帧已生成", shot_result.last_frame_path)
                _set_stage(job_id, "video", "首尾帧视频", "running", "生成首尾帧控制视频")
            if shot_result.video_path:
                status = "warning" if shot_result.warnings else "completed"
                _set_stage(job_id, "video", "首尾帧视频", status, "视频片段已生成", shot_result.video_path)
            warnings.extend(shot_result.warnings)
            _jobs[job_id]["latest_shot"] = shot_result.__dict__

        pipeline = PipelineV5(style=style or "anime")
        result = pipeline.run(
            project_id=project_id,
            generate_image=True,
            generate_video=True,
            generate_character_sheets=False,
            generate_shot_tables=True,
            on_shot=on_shot,
        )

        final_video = result.final_video or next((s.video_path for s in result.shots if s.video_path), "")
        _set_stage(
            job_id,
            "export",
            "输出成片文件",
            "completed" if final_video else "failed",
            "最终视频已就绪" if final_video else "没有生成视频文件",
            final_video,
        )

        _jobs[job_id].update({
            "status": "completed" if final_video else "failed",
            "progress": 1.0,
            "message": "V5 一键生成完成" if final_video else "V5 生成失败：没有视频文件",
            "finished_at": datetime.now().isoformat(),
            "output_dir": result.output_dir,
            "final_video": final_video,
            "warnings": warnings,
            "result": result.to_dict(),
        })
    except Exception as e:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["message"] = str(e)
        _jobs[job_id]["finished_at"] = datetime.now().isoformat()
        logger.exception(f"[Pipeline] Job {job_id} failed")


def _create_job(novel_path: Path) -> str:
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "job_id": job_id,
        "novel": novel_path.name,
        "status": "pending",
        "progress": 0.0,
        "message": "已加入队列",
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "output_dir": str(OUTPUT_DIR / novel_path.stem),
        "final_video": "",
        "warnings": [],
        "stages": {},
    }
    return job_id


@router.post("/run")
async def run_pipeline(request: PipelineRunRequest):
    novel_path = Path(request.novel_path)
    if not novel_path.exists():
        raise HTTPException(status_code=404, detail=f"Novel not found: {request.novel_path}")

    job_id = _create_job(novel_path)
    thread = threading.Thread(
        target=_run_pipeline_thread,
        args=(job_id, str(novel_path), request.style, request.max_shots),
        daemon=True,
    )
    thread.start()

    logger.info(f"[Pipeline] V5 job {job_id} started for {novel_path.name}")
    return {"job_id": job_id, "status": "pending", "novel": novel_path.name}


@router.post("/upload")
async def upload_and_run(file: UploadFile = File(...), style: str = Form(None)):
    if not file.filename or not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files accepted")

    content = await file.read()
    novel_path = NOVELS_DIR / file.filename
    novel_path.write_bytes(content)

    job_id = _create_job(novel_path)
    thread = threading.Thread(
        target=_run_pipeline_thread,
        args=(job_id, str(novel_path), style, 1),
        daemon=True,
    )
    thread.start()

    logger.info(f"[Pipeline] Upload + V5 start: {file.filename} -> job {job_id}")
    return {"job_id": job_id, "status": "pending", "novel": file.filename}


@router.get("/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _jobs[job_id]
    return {**job, "stage_list": _stage_list(job_id), "output": job.get("output", "")[-2000:]}


@router.get("/novels")
async def list_novels():
    novels = []
    if NOVELS_DIR.exists():
        for f in sorted(NOVELS_DIR.glob("*.txt")):
            novels.append({
                "name": f.name,
                "path": str(f),
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
    for f in sorted(PROJECT_ROOT.glob("novel*.txt")):
        novels.append({
            "name": f.name,
            "path": str(f),
            "size": f.stat().st_size,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return {"total": len(novels), "novels": novels}


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    if _jobs[job_id]["status"] in ("running", "pending"):
        _jobs[job_id]["status"] = "cancelled"
        _jobs[job_id]["message"] = "已取消"
    return {"status": "cancelled"}
