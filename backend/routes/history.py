"""History management API routes.

Provides endpoints for clearing project history:
- DELETE /api/history/{project_id} - Clear a single project's history
- DELETE /api/history/all - Clear all history (full reset)
- GET /api/history/stats - Get history statistics
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/history", tags=["history"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ClearHistoryResponse(BaseModel):
    project_id: str = ""
    cleared_jobs: int = 0
    cleared_artifacts: int = 0
    cleared_steps: int = 0
    cleared_files: int = 0
    freed_bytes: int = 0
    message: str = ""


class HistoryStats(BaseModel):
    total_jobs: int = 0
    total_artifacts: int = 0
    total_steps: int = 0
    total_projects: int = 0
    storage_bytes: int = 0
    db_path: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_config(request: Request):
    return getattr(request.app.state, "config", None)


def _get_db(request: Request):
    db = getattr(request.app.state, "orchestration_db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="数据库未就绪")
    return db


def _get_repo(request: Request):
    repo = getattr(request.app.state, "repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="仓库未就绪")
    return repo


def _resolve_project_root(request: Request, project_id: str) -> Path:
    config = _get_config(request)
    return Path(config.project_root) / project_id if config else Path("projects") / project_id


def _count_dir_files(directory: Path) -> tuple[int, int]:
    """Count files and total size in a directory recursively.

    Returns (file_count, total_bytes).
    """
    if not directory.exists():
        return 0, 0
    file_count = 0
    total_bytes = 0
    for item in directory.rglob("*"):
        if item.is_file():
            file_count += 1
            try:
                total_bytes += item.stat().st_size
            except OSError:
                pass
    return file_count, total_bytes


def _delete_project_outputs(project_root: Path) -> tuple[int, int]:
    """Delete the outputs directory of a project.

    Returns (deleted_file_count, freed_bytes).
    """
    outputs_dir = project_root / "outputs"
    if not outputs_dir.exists():
        return 0, 0

    file_count, total_bytes = _count_dir_files(outputs_dir)

    try:
        shutil.rmtree(outputs_dir)
        logger.info("Deleted project outputs: %s (%d files, %d bytes)",
                    outputs_dir, file_count, total_bytes)
    except Exception as exc:
        logger.error("Failed to delete outputs: %s", exc)
        raise HTTPException(status_code=500, detail=f"删除输出文件失败: {exc}")

    return file_count, total_bytes


def _clear_db_project_history(db, project_id: str) -> dict[str, int]:
    """Clear all database records for a specific project.

    Uses CASCADE delete: deleting jobs automatically removes job_steps,
    artifacts, and checkpoints.

    Returns dict with cleared counts.
    """
    counts = {"jobs": 0, "steps": 0, "artifacts": 0}

    with db.connect() as conn:
        # Count records before deletion
        row = conn.execute(
            "SELECT COUNT(*) as c FROM jobs WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        counts["jobs"] = row["c"] if row else 0

        row = conn.execute(
            """SELECT COUNT(*) as c FROM job_steps
               WHERE job_id IN (SELECT id FROM jobs WHERE project_id = ?)""",
            (project_id,),
        ).fetchone()
        counts["steps"] = row["c"] if row else 0

        row = conn.execute(
            """SELECT COUNT(*) as c FROM artifacts
               WHERE job_id IN (SELECT id FROM jobs WHERE project_id = ?)""",
            (project_id,),
        ).fetchone()
        counts["artifacts"] = row["c"] if row else 0

        # Delete project workspace record
        conn.execute(
            "DELETE FROM project_workspaces WHERE project_id = ?",
            (project_id,),
        )

        # Delete stage automation settings
        conn.execute(
            "DELETE FROM stage_automation WHERE project_id = ?",
            (project_id,),
        )

        # Delete jobs (CASCADE removes steps, artifacts, checkpoints)
        conn.execute(
            "DELETE FROM jobs WHERE project_id = ?",
            (project_id,),
        )

        # Also delete artifacts that were tagged with project_id directly
        conn.execute(
            "DELETE FROM artifacts WHERE project_id = ?",
            (project_id,),
        )

        conn.commit()

    logger.info("Cleared DB history for project %s: %s", project_id, counts)
    return counts


def _clear_all_db_history(db) -> dict[str, int]:
    """Clear ALL database history (full reset).

    Returns dict with cleared counts.
    """
    counts = {"jobs": 0, "steps": 0, "artifacts": 0}

    with db.connect() as conn:
        row = conn.execute("SELECT COUNT(*) as c FROM jobs").fetchone()
        counts["jobs"] = row["c"] if row else 0

        row = conn.execute("SELECT COUNT(*) as c FROM job_steps").fetchone()
        counts["steps"] = row["c"] if row else 0

        row = conn.execute("SELECT COUNT(*) as c FROM artifacts").fetchone()
        counts["artifacts"] = row["c"] if row else 0

        # Delete all records
        conn.execute("DELETE FROM jobs")
        conn.execute("DELETE FROM project_workspaces")
        conn.execute("DELETE FROM stage_automation")
        conn.execute("DELETE FROM artifacts")

        conn.commit()

    logger.info("Cleared ALL DB history: %s", counts)
    return counts


def _delete_all_project_outputs(projects_root: Path) -> tuple[int, int]:
    """Delete outputs directories from all projects.

    Returns (deleted_file_count, freed_bytes).
    """
    total_files = 0
    total_bytes = 0

    if not projects_root.exists():
        return 0, 0

    for project_dir in projects_root.iterdir():
        if not project_dir.is_dir():
            continue
        outputs_dir = project_dir / "outputs"
        if outputs_dir.exists():
            f, b = _count_dir_files(outputs_dir)
            total_files += f
            total_bytes += b
            try:
                shutil.rmtree(outputs_dir)
            except Exception as exc:
                logger.warning("Failed to remove %s: %s", outputs_dir, exc)

    return total_files, total_bytes


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=HistoryStats)
async def get_history_stats(request: Request) -> HistoryStats:
    """Get history statistics including record counts and storage usage."""
    db = _get_db(request)
    config = _get_config(request)
    projects_root = Path(config.project_root) if config else Path("projects")

    with db.connect() as conn:
        jobs_count = conn.execute("SELECT COUNT(*) as c FROM jobs").fetchone()["c"]
        steps_count = conn.execute("SELECT COUNT(*) as c FROM job_steps").fetchone()["c"]
        artifacts_count = conn.execute("SELECT COUNT(*) as c FROM artifacts").fetchone()["c"]
        projects_count = conn.execute(
            "SELECT COUNT(DISTINCT project_id) as c FROM jobs"
        ).fetchone()["c"]

    storage_bytes = 0
    if projects_root.exists():
        for project_dir in projects_root.iterdir():
            if project_dir.is_dir():
                _, size = _count_dir_files(project_dir / "outputs")
                storage_bytes += size

    db_path = str(Path("storage/orchestrator.db").resolve())

    return HistoryStats(
        total_jobs=jobs_count,
        total_artifacts=artifacts_count,
        total_steps=steps_count,
        total_projects=projects_count,
        storage_bytes=storage_bytes,
        db_path=db_path,
    )


@router.delete("/{project_id}", response_model=ClearHistoryResponse)
async def clear_project_history(
    project_id: str,
    request: Request,
    clear_outputs: bool = True,
) -> ClearHistoryResponse:
    """Clear all history for a specific project.

    - Deletes all job records, steps, artifacts, and checkpoints (CASCADE)
    - Removes project workspace and stage automation records
    - Optionally deletes output files (images, videos, audio)

    Args:
        project_id: Project identifier.
        clear_outputs: If True (default), also delete the outputs directory.
    """
    db = _get_db(request)
    config = _get_config(request)
    project_root = _resolve_project_root(request, project_id)

    # Clear database records
    db_counts = _clear_db_project_history(db, project_id)

    # Clear output files
    file_count = 0
    freed_bytes = 0
    if clear_outputs:
        file_count, freed_bytes = _delete_project_outputs(project_root)

    # Also clear production plan if it exists
    plan_path = project_root / "production_plan.json"
    plan_deleted = False
    if plan_path.exists():
        try:
            plan_path.unlink()
            plan_deleted = True
        except Exception as exc:
            logger.warning("Failed to delete production plan: %s", exc)

    message_parts = [
        f"已清除 {db_counts['jobs']} 条任务记录",
        f"{db_counts['steps']} 个步骤",
        f"{db_counts['artifacts']} 个产物",
    ]
    if clear_outputs and file_count > 0:
        message_parts.append(f"{file_count} 个文件 ({freed_bytes / 1024 / 1024:.1f}MB)")
    if plan_deleted:
        message_parts.append("生产计划已删除")

    return ClearHistoryResponse(
        project_id=project_id,
        cleared_jobs=db_counts["jobs"],
        cleared_artifacts=db_counts["artifacts"],
        cleared_steps=db_counts["steps"],
        cleared_files=file_count,
        freed_bytes=freed_bytes,
        message="，".join(message_parts),
    )


@router.delete("/all", response_model=ClearHistoryResponse)
async def clear_all_history(
    request: Request,
    clear_outputs: bool = True,
) -> ClearHistoryResponse:
    """Clear ALL history - full system reset.

    WARNING: This deletes all projects' history and output files.

    - Deletes all job records, steps, artifacts, and checkpoints
    - Removes all project workspace and stage automation records
    - Optionally deletes all output files from all projects
    """
    db = _get_db(request)
    config = _get_config(request)
    projects_root = Path(config.project_root) if config else Path("projects")

    # Clear all database records
    db_counts = _clear_all_db_history(db)

    # Clear all output files
    file_count = 0
    freed_bytes = 0
    if clear_outputs:
        file_count, freed_bytes = _delete_all_project_outputs(projects_root)

    # Also clear all production plans
    plans_deleted = 0
    if projects_root.exists():
        for project_dir in projects_root.iterdir():
            if not project_dir.is_dir():
                continue
            plan_path = project_dir / "production_plan.json"
            if plan_path.exists():
                try:
                    plan_path.unlink()
                    plans_deleted += 1
                except Exception:
                    pass

    message_parts = [
        f"已清除 {db_counts['jobs']} 条任务记录",
        f"{db_counts['steps']} 个步骤",
        f"{db_counts['artifacts']} 个产物",
    ]
    if clear_outputs and file_count > 0:
        message_parts.append(f"{file_count} 个文件 ({freed_bytes / 1024 / 1024:.1f}MB)")
    if plans_deleted > 0:
        message_parts.append(f"{plans_deleted} 个生产计划")

    return ClearHistoryResponse(
        project_id="ALL",
        cleared_jobs=db_counts["jobs"],
        cleared_artifacts=db_counts["artifacts"],
        cleared_steps=db_counts["steps"],
        cleared_files=file_count,
        freed_bytes=freed_bytes,
        message="，".join(message_parts),
    )
