from __future__ import annotations

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
        asset = self.repo.update_project_asset_director(
            project_id,
            asset_id,
            value.model_dump(mode="json"),
        )
        if asset is None:
            raise AssetNotFound
        return asset

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
