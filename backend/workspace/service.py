from __future__ import annotations

import json
from pathlib import Path

from backend.migration.scanner import ProjectScanner, ScannedProject
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.enums import JOB_ACTIVE
from backend.orchestration.repository import ReviewJobNotFound, ReviewTransitionConflict
from backend.orchestration.service import JobService
from backend.orchestration.schemas import JobDetail
from backend.orchestration.worker import SSEBroadcaster
from backend.workspace.models import (
    DirectorSettings,
    ProjectAsset,
    StageAutomation,
    StageKey,
    StageSummary,
    WorkspaceSnapshot,
)
from backend.workspace.repository import WorkspaceRepository


class WorkspaceService:
    def __init__(
        self,
        db: OrchestrationDatabase,
        repo: WorkspaceRepository,
        project_scanner: ProjectScanner | None = None,
        broadcaster: SSEBroadcaster | None = None,
        projects_root: str | Path = "projects",
        job_service: JobService | None = None,
    ):
        self.db = db
        self.repo = repo
        self.project_scanner = project_scanner or ProjectScanner("projects")
        self.broadcaster = broadcaster
        self.projects_root = Path(projects_root)
        self.job_service = job_service

    def get_snapshot(self, project_id: str) -> WorkspaceSnapshot:
        jobs = self._project_jobs(project_id)
        project = self.repo.get_project(project_id)
        if project is None:
            scanned = self._find_scanned_project(project_id, jobs)
            source_path = scanned.source_path if scanned else next(
                (job["input_path"] for job in jobs if job["input_path"]), ""
            )
            self.repo.upsert_project(
                project_id,
                title=scanned.name if scanned else None,
                source_path=source_path,
            )
            project = self.repo.get_project(project_id)

        automations = self.repo.get_all_stage_automation(project_id)
        steps = self._project_steps(project_id)
        stage_summaries = [
            self._stage_summary(automation, [step for step in steps if step["stage_key"] == automation.stage_key.value])
            for automation in automations
        ]
        active_jobs = sum(job["status"] in JOB_ACTIVE for job in jobs)
        pending_reviews = sum(job["status"] == "waiting_review" for job in jobs)
        progress = sum(job["progress"] for job in jobs) / len(jobs) if jobs else 0

        return WorkspaceSnapshot(
            project_id=project_id,
            title=project["title"],
            source_path=project["source_path"],
            version=f"v{project['version']:02d}",
            progress=progress,
            pending_reviews=pending_reviews,
            active_jobs=active_jobs,
            stages=stage_summaries,
            system_health={"database": "ok", "jobs": len(jobs)},
        )

    def update_automation(self, project_id: str, value: StageAutomation) -> StageAutomation:
        if self.repo.get_project(project_id) is None:
            scanned = self._find_scanned_project(project_id, self._project_jobs(project_id))
            self.repo.upsert_project(
                project_id,
                title=scanned.name if scanned else None,
                source_path=scanned.source_path if scanned else None,
            )
        self.repo.upsert_stage_automation(project_id, value)
        if self.broadcaster:
            payload = {
                "project_id": project_id,
                "stage_key": value.stage_key.value,
                "automation": value.model_dump(mode="json"),
            }
            for job in self._project_jobs(project_id):
                self.broadcaster.broadcast(job["id"], "automation_changed", payload)
        return value

    def list_assets(
        self,
        project_id: str,
        *,
        kind: str | None = None,
        stage_key: str | None = None,
        scene_id: str | None = None,
        shot_id: str | None = None,
        quality_status: str | None = None,
        active: bool | None = None,
    ) -> list[ProjectAsset]:
        return self.repo.list_project_assets(
            project_id,
            kind=kind,
            stage_key=stage_key,
            scene_id=scene_id,
            shot_id=shot_id,
            quality_status=quality_status,
            active=active,
        )

    def update_director_settings(
        self,
        project_id: str,
        asset_id: int,
        value: DirectorSettings,
    ) -> ProjectAsset:
        current = self.repo.get_project_asset(project_id, asset_id)
        if current is None:
            raise AssetNotFound

        director = value.model_dump(mode="json")
        if current.shot_id:
            self._sync_director_to_production_plan(project_id, current.shot_id, director)

        asset = self.repo.update_project_asset_director(project_id, asset_id, director)
        if asset is None:
            raise AssetNotFound
        return asset

    def _sync_director_to_production_plan(
        self,
        project_id: str,
        shot_id: str,
        director: dict[str, object],
    ) -> None:
        project_root = (self.projects_root / project_id).resolve()
        projects_root = self.projects_root.resolve()
        try:
            project_root.relative_to(projects_root)
        except ValueError:
            raise DirectorRuntimeSyncError("项目路径越界")

        plan_path = project_root / "production_plan.json"
        if not plan_path.is_file():
            return

        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise DirectorRuntimeSyncError("production_plan.json 无法读取") from error

        shots = plan.get("shots")
        if not isinstance(shots, list):
            raise DirectorRuntimeSyncError("production_plan.json 缺少 shots")

        target = next((shot for shot in shots if isinstance(shot, dict) and shot.get("id") == shot_id), None)
        if target is None:
            return

        base_prompt = str(
            target.get("director_base_positive_prompt")
            or target.get("positive_prompt")
            or ""
        ).strip()
        target["director_base_positive_prompt"] = base_prompt
        target["director"] = director

        movement_strength = int(director.get("movement_strength", 65) or 0)
        motion_level = _director_motion_level(movement_strength)
        motion_bucket_id = _MOTION_BUCKET_BY_LEVEL[motion_level]
        camera_movement = str(director.get("camera_movement") or "").strip()
        emotions = [str(item).strip() for item in director.get("emotion", []) if str(item).strip()]

        target["camera_movement"] = camera_movement
        target["camera"] = camera_movement
        target["motion_level"] = motion_level
        target["motion_bucket_id"] = motion_bucket_id
        target["director_composition"] = str(director.get("composition") or "")
        target["director_shot_size"] = str(director.get("shot_size") or "")
        target["director_focal_length"] = str(director.get("focal_length") or "")
        target["director_lighting"] = str(director.get("lighting") or "")
        target["director_emotion"] = emotions

        clauses = [
            f"构图：{target['director_composition']}" if target["director_composition"] else "",
            f"景别：{target['director_shot_size']}" if target["director_shot_size"] else "",
            f"运镜：{camera_movement}" if camera_movement else "",
            f"焦段：{target['director_focal_length']}" if target["director_focal_length"] else "",
            f"光线：{target['director_lighting']}" if target["director_lighting"] else "",
            f"情绪：{'、'.join(emotions)}" if emotions else "",
            str(director.get("prompt") or "").strip(),
        ]
        director_clause = "，".join(part for part in clauses if part)
        target["positive_prompt"] = (
            f"{base_prompt}。导演控制：{director_clause}" if base_prompt and director_clause
            else director_clause or base_prompt
        )

        tmp_path = plan_path.with_suffix(".json.tmp")
        try:
            tmp_path.write_text(
                json.dumps(plan, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(plan_path)
        except OSError as error:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise DirectorRuntimeSyncError("production_plan.json 写入失败") from error

    def get_asset_media(self, project_id: str, asset_id: int) -> tuple[Path, str] | None:
        stored_path = self.repo.get_project_asset_stored_path(project_id, asset_id)
        if stored_path is None:
            return None
        projects_root = self.projects_root.resolve()
        project_root = (projects_root / project_id).resolve()
        try:
            project_root.relative_to(projects_root)
        except ValueError:
            return None
        raw_path = Path(stored_path)
        if raw_path.is_absolute():
            candidate = raw_path.resolve()
        else:
            legacy_candidate = raw_path.resolve()
            try:
                legacy_candidate.relative_to(project_root)
            except ValueError:
                parts = raw_path.parts
                if (
                    len(parts) >= 2
                    and parts[0].casefold() == projects_root.name.casefold()
                    and parts[1].casefold() == project_id.casefold()
                ):
                    candidate = project_root.joinpath(*parts[2:]).resolve()
                else:
                    candidate = (project_root / raw_path).resolve()
            else:
                candidate = legacy_candidate
        try:
            candidate.relative_to(project_root)
        except ValueError:
            return None
        if not candidate.is_file():
            return None
        media_type = _MEDIA_TYPES.get(candidate.suffix.lower())
        if media_type is None:
            raise UnsupportedAssetMedia
        return candidate, media_type

    def regenerate_asset(self, project_id: str, asset_id: int) -> JobDetail:
        asset = self.repo.get_project_asset(project_id, asset_id)
        if asset is None:
            raise AssetNotFound
        if self.job_service is None:
            raise JobServiceUnavailable
        try:
            return self.job_service.review(
                asset.job_id,
                "retry",
                expected_step_id=asset.step_id,
                expected_project_id=project_id,
                expected_asset_id=asset.id,
            )
        except ReviewTransitionConflict as error:
            raise AssetNotReviewable
        except ReviewJobNotFound as error:
            raise AssetNotFound from error

    def _project_jobs(self, project_id: str) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM jobs WHERE project_id=?", (project_id,)).fetchall()
        return [dict(row) for row in rows]

    def _project_steps(self, project_id: str) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT job_steps.stage_key, job_steps.status, job_steps.progress
                   FROM job_steps
                   INNER JOIN jobs ON jobs.id = job_steps.job_id
                   WHERE jobs.project_id=?""",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _find_scanned_project(self, project_id: str, jobs: list[dict]) -> ScannedProject | None:
        scanned_projects = self.project_scanner.scan()
        for project in scanned_projects:
            if project.name == project_id:
                return project

        input_paths = [Path(job["input_path"]).resolve() for job in jobs if job["input_path"]]
        for project in scanned_projects:
            project_path = Path(project.source_path).resolve()
            if any(path == project_path or project_path in path.parents for path in input_paths):
                return project

        return scanned_projects[0] if len(scanned_projects) == 1 else None

    @staticmethod
    def _stage_summary(automation: StageAutomation, steps: list[dict]) -> StageSummary:
        if not steps:
            return StageSummary(stage_key=automation.stage_key, automation=automation)
        statuses = [step["status"] for step in steps]
        status = next(
            (
                candidate
                for candidate in ("waiting_review", "running", "queued", "retry_wait", "failed", "completed")
                if candidate in statuses
            ),
            "pending",
        )
        return StageSummary(
            stage_key=automation.stage_key,
            status=status,
            progress=sum(step["progress"] for step in steps) / len(steps),
            waiting_review=statuses.count("waiting_review"),
            automation=automation,
        )


class UnsupportedAssetMedia(Exception):
    pass


class AssetNotFound(Exception):
    pass


class AssetNotReviewable(Exception):
    pass


class JobServiceUnavailable(Exception):
    pass


class DirectorRuntimeSyncError(Exception):
    pass


def _director_motion_level(strength: int) -> int:
    value = max(0, min(100, int(strength)))
    if value <= 10:
        return 0
    if value <= 30:
        return 1
    if value <= 50:
        return 2
    if value <= 70:
        return 3
    if value <= 85:
        return 4
    return 5


_MOTION_BUCKET_BY_LEVEL = {0: 40, 1: 60, 2: 105, 3: 140, 4: 175, 5: 195}

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json",
    ".srt": "application/x-subrip; charset=utf-8",
    ".vtt": "text/vtt; charset=utf-8",
    ".ass": "text/plain; charset=utf-8",
}
