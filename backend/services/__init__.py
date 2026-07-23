"""
Services Layer — Business logic orchestration (Part 8)

Thin service layer that coordinates between API routes,
repositories, agents, workflow engine, and providers.
No business logic here — that belongs in agents and workflow.

Each service corresponds to a domain aggregate root.
"""

from __future__ import annotations

from typing import Any, Optional

from backend.database import DatabaseManager
from backend.repositories import (
    ProjectRepository,
    StoryRepository,
    CharacterRepository,
    SceneRepository,
    StoryboardRepository,
    ShotRepository,
    AssetRepository,
    JobRepository,
    ReviewRepository,
)
from backend.events import (
    event_bus,
    ProjectEvent,
    JobEvent,
    AssetEvent,
)


class ProjectService:
    """Project lifecycle management."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    async def create_project(
        self, name: str, description: str = "", settings: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Create a new project."""
        async with self.db.session() as session:
            repo = ProjectRepository(session)
            project = await repo.create(
                name=name,
                description=description,
                settings=settings or {},
                status="draft",
            )
            await session.commit()

            await event_bus.publish(
                ProjectEvent(
                    project_id=project.project_id,
                    source="project_service",
                    payload={"action": "created", "name": name},
                )
            )

            return self._to_dict(project)

    async def get_project(self, project_id: str) -> Optional[dict[str, Any]]:
        """Get a project by ID."""
        async with self.db.session() as session:
            repo = ProjectRepository(session)
            project = await repo.get(project_id)
            return self._to_dict(project) if project else None

    async def list_projects(
        self, offset: int = 0, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List active projects."""
        async with self.db.session() as session:
            repo = ProjectRepository(session)
            projects = await repo.find_active()
            return [self._to_dict(p) for p in projects[offset : offset + limit]]

    async def delete_project(self, project_id: str) -> bool:
        """Soft-delete a project."""
        async with self.db.session() as session:
            repo = ProjectRepository(session)
            result = await repo.delete(project_id)
            await session.commit()

            if result:
                await event_bus.publish(
                    ProjectEvent(
                        project_id=project_id,
                        source="project_service",
                        payload={"action": "deleted"},
                    )
                )
            return result

    @staticmethod
    def _to_dict(project: Any) -> dict[str, Any]:
        return {
            "project_id": project.project_id,
            "name": project.name,
            "description": project.description,
            "status": project.status,
            "settings": project.settings,
            "created_at": project.created_at.isoformat() if project.created_at else "",
            "updated_at": project.updated_at.isoformat() if project.updated_at else "",
        }


class CharacterService:
    """Character management operations."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    async def create_character(
        self, project_id: str, name: str, role: str = "supporting", **kwargs: Any
    ) -> dict[str, Any]:
        """Create a new character in a project."""
        async with self.db.session() as session:
            repo = CharacterRepository(session)
            character = await repo.create(
                project_id=project_id,
                name=name,
                role=role,
                appearance=kwargs.get("appearance", ""),
                personality=kwargs.get("personality", ""),
                backstory=kwargs.get("backstory", ""),
                relationships=kwargs.get("relationships", []),
                voice_profile=kwargs.get("voice_profile", ""),
                reference_images=kwargs.get("reference_images", []),
            )
            await session.commit()
            return self._to_dict(character)

    async def list_characters(self, project_id: str) -> list[dict[str, Any]]:
        """List all characters in a project."""
        async with self.db.session() as session:
            repo = CharacterRepository(session)
            characters = await repo.find_by_project(project_id)
            return [self._to_dict(c) for c in characters]

    async def get_character(
        self, character_id: str
    ) -> Optional[dict[str, Any]]:
        """Get a character by ID."""
        async with self.db.session() as session:
            repo = CharacterRepository(session)
            character = await repo.get(character_id)
            return self._to_dict(character) if character else None

    @staticmethod
    def _to_dict(character: Any) -> dict[str, Any]:
        return {
            "character_id": character.character_id,
            "project_id": character.project_id,
            "name": character.name,
            "role": character.role,
            "archetype": character.archetype,
            "appearance": character.appearance,
            "personality": character.personality,
            "backstory": character.backstory,
            "relationships": character.relationships,
            "voice_profile": character.voice_profile,
            "reference_images": character.reference_images,
            "version": character.version,
            "status": character.status,
            "created_at": character.created_at.isoformat() if character.created_at else "",
            "updated_at": character.updated_at.isoformat() if character.updated_at else "",
        }


class StoryboardService:
    """Storyboard and shot management."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    async def create_storyboard(
        self, project_id: str, name: str = ""
    ) -> dict[str, Any]:
        """Create a new storyboard."""
        async with self.db.session() as session:
            repo = StoryboardRepository(session)
            storyboard = await repo.create(
                project_id=project_id,
                name=name,
                status="draft",
            )
            await session.commit()
            return self._to_dict(storyboard)

    async def add_shot(
        self,
        storyboard_id: str,
        description: str = "",
        shot_number: int = 1,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Add a shot to a storyboard."""
        async with self.db.session() as session:
            repo = ShotRepository(session)
            shot = await repo.create(
                storyboard_id=storyboard_id,
                description=description,
                shot_number=shot_number,
                dialogue=kwargs.get("dialogue", ""),
                camera_angle=kwargs.get("camera_angle", ""),
                duration_frames=kwargs.get("duration_frames", 72),
                planned_duration_seconds=kwargs.get("planned_duration_seconds", 3.0),
            )
            await session.commit()
            return self._to_shot_dict(shot)

    async def list_storyboards(self, project_id: str) -> list[dict[str, Any]]:
        """List storyboards in a project."""
        async with self.db.session() as session:
            repo = StoryboardRepository(session)
            storyboards = await repo.find_by_project(project_id)
            return [self._to_dict(s) for s in storyboards]

    async def list_shots(self, storyboard_id: str) -> list[dict[str, Any]]:
        """List all shots in a storyboard."""
        async with self.db.session() as session:
            repo = ShotRepository(session)
            shots = await repo.find_by_storyboard(storyboard_id)
            return [self._to_shot_dict(s) for s in shots]

    @staticmethod
    def _to_dict(storyboard: Any) -> dict[str, Any]:
        return {
            "storyboard_id": storyboard.storyboard_id,
            "project_id": storyboard.project_id,
            "name": storyboard.name,
            "version": storyboard.version,
            "status": storyboard.status,
            "settings": storyboard.settings,
            "created_at": storyboard.created_at.isoformat() if storyboard.created_at else "",
        }

    @staticmethod
    def _to_shot_dict(shot: Any) -> dict[str, Any]:
        return {
            "shot_id": shot.shot_id,
            "storyboard_id": shot.storyboard_id,
            "scene_id": shot.scene_id or "",
            "shot_number": shot.shot_number,
            "description": shot.description,
            "dialogue": shot.dialogue,
            "camera_angle": shot.camera_angle,
            "duration_frames": shot.duration_frames,
            "planned_duration_seconds": shot.planned_duration_seconds,
            "status": shot.status,
        }


class AssetService:
    """Asset management operations."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    async def create_asset(
        self,
        project_id: str,
        asset_type: str,
        file_path: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Register a new asset."""
        async with self.db.session() as session:
            repo = AssetRepository(session)
            asset = await repo.create(
                project_id=project_id,
                asset_type=asset_type,
                file_path=file_path,
                file_name=kwargs.get("file_name", ""),
                mime_type=kwargs.get("mime_type", ""),
                file_size_bytes=kwargs.get("file_size_bytes", 0),
                width=kwargs.get("width", 0),
                height=kwargs.get("height", 0),
                duration_seconds=kwargs.get("duration_seconds", 0.0),
                sha256_hash=kwargs.get("sha256_hash", ""),
                metadata=kwargs.get("metadata", {}),
                quality_score=kwargs.get("quality_score", 0.0),
                business_role=kwargs.get("business_role", ""),
                lifecycle_role=kwargs.get("lifecycle_role", "working"),
            )
            await session.commit()

            await event_bus.publish(
                AssetEvent(
                    project_id=project_id,
                    asset_id=asset.asset_id,
                    source="asset_service",
                    payload={"action": "created", "asset_type": asset_type},
                )
            )

            return self._to_dict(asset)

    async def list_assets(
        self, project_id: str, asset_type: str = ""
    ) -> list[dict[str, Any]]:
        """List assets in a project."""
        async with self.db.session() as session:
            repo = AssetRepository(session)
            if asset_type:
                assets = await repo.find_by_type(project_id, asset_type)
            else:
                assets = await repo.find_by_project(project_id)
            return [self._to_dict(a) for a in assets]

    async def get_asset(self, asset_id: str) -> Optional[dict[str, Any]]:
        """Get an asset by ID."""
        async with self.db.session() as session:
            repo = AssetRepository(session)
            asset = await repo.get(asset_id)
            return self._to_dict(asset) if asset else None

    @staticmethod
    def _to_dict(asset: Any) -> dict[str, Any]:
        return {
            "asset_id": asset.asset_id,
            "project_id": asset.project_id,
            "asset_type": asset.asset_type,
            "business_role": asset.business_role,
            "lifecycle_role": asset.lifecycle_role,
            "file_path": asset.file_path,
            "file_name": asset.file_name,
            "mime_type": asset.mime_type,
            "file_size_bytes": asset.file_size_bytes,
            "width": asset.width,
            "height": asset.height,
            "duration_seconds": asset.duration_seconds,
            "sha256_hash": asset.sha256_hash,
            "metadata": asset.metadata,
            "quality_score": asset.quality_score,
            "version": asset.version,
            "status": asset.status,
            "created_at": asset.created_at.isoformat() if asset.created_at else "",
        }


class JobService:
    """Job submission and monitoring."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    async def submit_job(
        self,
        project_id: str,
        job_type: str,
        input_data: dict[str, Any],
        priority: int = 0,
    ) -> dict[str, Any]:
        """Submit a new job."""
        async with self.db.session() as session:
            repo = JobRepository(session)
            job = await repo.create(
                project_id=project_id,
                job_type=job_type,
                input_data=input_data,
                priority=priority,
                status="pending",
            )
            await session.commit()

            await event_bus.publish(
                JobEvent(
                    project_id=project_id,
                    job_id=job.job_id,
                    source="job_service",
                    payload={"action": "submitted", "job_type": job_type},
                )
            )

            return self._to_dict(job)

    async def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        """Get a job by ID."""
        async with self.db.session() as session:
            repo = JobRepository(session)
            job = await repo.get(job_id)
            return self._to_dict(job) if job else None

    async def list_jobs(
        self, project_id: str | None = None, status: str = ""
    ) -> list[dict[str, Any]]:
        """List jobs with optional filters."""
        async with self.db.session() as session:
            repo = JobRepository(session)
            if project_id:
                jobs = await repo.find_by_project(project_id)
            elif status:
                jobs = await repo.find_by_status(status)
            else:
                jobs = await repo.list()
            return [self._to_dict(j) for j in jobs]

    @staticmethod
    def _to_dict(job: Any) -> dict[str, Any]:
        return {
            "job_id": job.job_id,
            "project_id": job.project_id,
            "job_type": job.job_type,
            "status": job.status,
            "priority": job.priority,
            "input_data": job.input_data,
            "output_data": job.output_data,
            "workflow_run_id": job.workflow_run_id,
            "error_message": job.error_message,
            "retry_count": job.retry_count,
            "progress": job.progress,
            "started_at": job.started_at.isoformat() if job.started_at else "",
            "completed_at": job.completed_at.isoformat() if job.completed_at else "",
            "created_at": job.created_at.isoformat() if job.created_at else "",
        }
