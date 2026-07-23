"""
Database Manager & ORM Models (Part 13)

SQLAlchemy 2.0 async ORM with aiosqlite/sqlite.
Defines all core entities as ORM models and provides
a DatabaseManager class for session lifecycle management.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    create_engine,
    event,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase, relationship

logger = logging.getLogger(__name__)


# ── Base ────────────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    pass


# ── ORM Models ──────────────────────────────────────────────────────────


class ProjectModel(Base):
    """Project aggregate root."""

    __tablename__ = "projects"

    project_id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    status = Column(String(32), default="draft")  # draft, in_progress, completed, archived
    settings = Column(JSON, default={})
    metadata_json = Column(JSON, default={})
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = Column(DateTime, nullable=True)

    # Relationships
    characters = relationship("CharacterModel", back_populates="project", lazy="selectin")
    storyboards = relationship("StoryboardModel", back_populates="project", lazy="selectin")
    assets = relationship("AssetModel", back_populates="project", lazy="selectin")
    jobs = relationship("JobModel", back_populates="project", lazy="selectin")
    stories = relationship("StoryModel", back_populates="project", lazy="selectin")


class StoryModel(Base):
    """Parsed story structure."""

    __tablename__ = "stories"

    story_id = Column(String(64), primary_key=True)
    project_id = Column(String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), default="")
    author = Column(String(255), default="")
    raw_text = Column(Text, default="")
    parsed_structure = Column(JSON, default={})  # JSON chapters, scenes, etc.
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("ProjectModel", back_populates="stories")


class CharacterModel(Base):
    """Character entity with memory and visual reference."""

    __tablename__ = "characters"

    character_id = Column(String(64), primary_key=True)
    project_id = Column(String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    role = Column(String(64), default="supporting")  # protagonist, antagonist, supporting
    archetype = Column(String(128), default="")
    appearance = Column(Text, default="")
    personality = Column(Text, default="")
    backstory = Column(Text, default="")
    relationships = Column(JSON, default=[])  # [{character_id, relation_type, description}]
    voice_profile = Column(Text, default="")
    reference_images = Column(JSON, default=[])  # [{asset_id, file_path, description}]
    model_settings = Column(JSON, default={})  # Character-specific model settings
    version = Column(Integer, default=1)
    status = Column(String(32), default="draft")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("ProjectModel", back_populates="characters")
    memory_records = relationship("MemoryRecordModel", back_populates="character", lazy="selectin")


class SceneModel(Base):
    """Scene entity with continuity data."""

    __tablename__ = "scenes"

    scene_id = Column(String(64), primary_key=True)
    story_id = Column(String(64), ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False)
    chapter_number = Column(Integer, default=1)
    scene_number = Column(Integer, default=1)
    title = Column(String(255), default="")
    description = Column(Text, default="")
    location = Column(String(255), default="")
    time_of_day = Column(String(64), default="")
    mood = Column(String(64), default="")
    weather = Column(String(64), default="")
    lighting_description = Column(Text, default="")
    camera_notes = Column(Text, default="")
    character_ids = Column(JSON, default=[])
    duration_estimate = Column(Integer, default=0)  # frames
    raw_text = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    story = relationship("StoryModel")
    memory_records = relationship("MemoryRecordModel", back_populates="scene", lazy="selectin")


class StoryboardModel(Base):
    """Storyboard container with shots."""

    __tablename__ = "storyboards"

    storyboard_id = Column(String(64), primary_key=True)
    project_id = Column(String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), default="")
    version = Column(Integer, default=1)
    status = Column(String(32), default="draft")
    settings = Column(JSON, default={})
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("ProjectModel", back_populates="storyboards")
    shots = relationship("ShotModel", back_populates="storyboard", lazy="selectin")


class ShotModel(Base):
    """Individual shot in a storyboard."""

    __tablename__ = "shots"

    shot_id = Column(String(64), primary_key=True)
    storyboard_id = Column(String(64), ForeignKey("storyboards.storyboard_id", ondelete="CASCADE"), nullable=False)
    scene_id = Column(String(64), ForeignKey("scenes.scene_id"), nullable=True)
    character_ids = Column(JSON, default=[])
    shot_number = Column(Integer, default=1)
    description = Column(Text, default="")
    dialogue = Column(Text, default="")
    sfx = Column(Text, default="")
    camera_angle = Column(String(128), default="")
    lighting_notes = Column(Text, default="")
    duration_frames = Column(Integer, default=72)
    planned_duration_seconds = Column(Float, default=3.0)
    image_asset_id = Column(String(64), nullable=True)
    video_asset_id = Column(String(64), nullable=True)
    status = Column(String(32), default="pending")  # pending, generating, completed, failed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    storyboard = relationship("StoryboardModel", back_populates="shots")


class AssetModel(Base):
    """Media asset (image, video, audio)."""

    __tablename__ = "assets"

    asset_id = Column(String(64), primary_key=True)
    project_id = Column(String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False)
    asset_type = Column(String(32), nullable=False)  # image, video, audio, other
    business_role = Column(String(64), default="")  # character_ref, bgm, sfx, voice, etc.
    lifecycle_role = Column(String(64), default="working")  # working, approved, revision, deprecated
    file_path = Column(Text, default="")
    file_name = Column(String(255), default="")
    mime_type = Column(String(64), default="")
    file_size_bytes = Column(Integer, default=0)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    duration_seconds = Column(Float, default=0.0)
    sha256_hash = Column(String(64), default="")
    metadata = Column(JSON, default={})
    quality_score = Column(Float, default=0.0)
    version = Column(Integer, default=1)
    status = Column(String(32), default="active")  # active, deleted
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("ProjectModel", back_populates="assets")


class JobModel(Base):
    """Async job tracking for AI generation tasks."""

    __tablename__ = "jobs"

    job_id = Column(String(64), primary_key=True)
    project_id = Column(String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False)
    job_type = Column(String(64), nullable=False)  # image_gen, video_gen, story_parse, etc.
    status = Column(String(32), default="pending")
    priority = Column(Integer, default=0)
    input_data = Column(JSON, default={})
    output_data = Column(JSON, default={})
    workflow_run_id = Column(String(64), nullable=True)
    error_message = Column(Text, default="")
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    progress = Column(Float, default=0.0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("ProjectModel", back_populates="jobs")


class MemoryRecordModel(Base):
    """Memory records for character/scene consistency."""

    __tablename__ = "memory_records"

    record_id = Column(String(64), primary_key=True)
    entity_type = Column(String(32), nullable=False)  # character, scene, global
    entity_id = Column(String(64), nullable=False)  # character_id or scene_id
    memory_type = Column(String(64), default="appearance")  # appearance, personality, setting, etc.
    key = Column(String(255), default="")
    value = Column(Text, default="")
    version = Column(Integer, default=1)
    importance = Column(Float, default=0.5)  # 0.0–1.0
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    character_id_fk = Column(String(64), ForeignKey("characters.character_id"), nullable=True)
    scene_id_fk = Column(String(64), ForeignKey("scenes.scene_id"), nullable=True)

    character = relationship("CharacterModel", back_populates="memory_records")
    scene = relationship("SceneModel", back_populates="memory_records")


class ReviewModel(Base):
    """Review/approval tracking."""

    __tablename__ = "reviews"

    review_id = Column(String(64), primary_key=True)
    project_id = Column(String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False)
    target_type = Column(String(32), nullable=False)  # shot, storyboard, export
    target_id = Column(String(64), nullable=False)
    decision = Column(String(32), default="pending")  # pending, approved, rejected, revision
    reviewer_notes = Column(Text, default="")
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("ProjectModel")


# ── Database Manager ───────────────────────────────────────────────────


class DatabaseManager:
    """
    Async database session manager.

    Provides:
    - Engine and session factory creation
    - Schema initialization
    - Context manager for sessions
    """

    def __init__(self, url: str = "sqlite+aiosqlite:///ai_manga.db", echo: bool = False) -> None:
        self.url = url
        self.engine = create_async_engine(
            url,
            echo=echo,
            future=True,
            pool_size=10,
            max_overflow=20,
        )
        self._session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def init_db(self) -> None:
        """Create all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")

    async def drop_all(self) -> None:
        """Drop all tables (use with caution!)."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.warning("All database tables dropped")

    def session(self) -> AsyncSession:
        """Get a new async session."""
        return self._session_factory()

    async def close(self) -> None:
        """Close the database connection."""
        await self.engine.dispose()


# ── Repositories ───────────────────────────────────────────────────────


class ProjectRepository:
    """Data access for projects."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs: Any) -> ProjectModel:
        project = ProjectModel(project_id=str(uuid.uuid4()), **kwargs)
        self.session.add(project)
        return project

    async def get(self, project_id: str) -> ProjectModel | None:
        result = await self.session.execute(
            select(ProjectModel).where(
                ProjectModel.project_id == project_id,
                ProjectModel.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def find_active(self) -> list[ProjectModel]:
        result = await self.session.execute(
            select(ProjectModel)
            .where(ProjectModel.deleted_at.is_(None))
            .order_by(ProjectModel.updated_at.desc())
        )
        return list(result.scalars().all())

    async def delete(self, project_id: str) -> bool:
        project = await self.get(project_id)
        if project:
            project.deleted_at = datetime.now(timezone.utc)
            return True
        return False


class CharacterRepository:
    """Data access for characters."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs: Any) -> CharacterModel:
        character = CharacterModel(character_id=str(uuid.uuid4()), **kwargs)
        self.session.add(character)
        return character

    async def get(self, character_id: str) -> CharacterModel | None:
        result = await self.session.execute(
            select(CharacterModel).where(CharacterModel.character_id == character_id)
        )
        return result.scalar_one_or_none()

    async def find_by_project(self, project_id: str) -> list[CharacterModel]:
        result = await self.session.execute(
            select(CharacterModel).where(CharacterModel.project_id == project_id)
        )
        return list(result.scalars().all())


class StoryRepository:
    """Data access for stories."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs: Any) -> StoryModel:
        story = StoryModel(story_id=str(uuid.uuid4()), **kwargs)
        self.session.add(story)
        return story

    async def find_by_project(self, project_id: str) -> list[StoryModel]:
        result = await self.session.execute(
            select(StoryModel).where(StoryModel.project_id == project_id)
        )
        return list(result.scalars().all())


class SceneRepository:
    """Data access for scenes."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs: Any) -> SceneModel:
        scene = SceneModel(scene_id=str(uuid.uuid4()), **kwargs)
        self.session.add(scene)
        return scene

    async def find_by_story(self, story_id: str) -> list[SceneModel]:
        result = await self.session.execute(
            select(SceneModel).where(SceneModel.story_id == story_id)
        )
        return list(result.scalars().all())


class StoryboardRepository:
    """Data access for storyboards."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs: Any) -> StoryboardModel:
        storyboard = StoryboardModel(storyboard_id=str(uuid.uuid4()), **kwargs)
        self.session.add(storyboard)
        return storyboard

    async def get(self, storyboard_id: str) -> StoryboardModel | None:
        result = await self.session.execute(
            select(StoryboardModel).where(StoryboardModel.storyboard_id == storyboard_id)
        )
        return result.scalar_one_or_none()

    async def find_by_project(self, project_id: str) -> list[StoryboardModel]:
        result = await self.session.execute(
            select(StoryboardModel).where(StoryboardModel.project_id == project_id)
        )
        return list(result.scalars().all())


class ShotRepository:
    """Data access for shots."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs: Any) -> ShotModel:
        shot = ShotModel(shot_id=str(uuid.uuid4()), **kwargs)
        self.session.add(shot)
        return shot

    async def find_by_storyboard(self, storyboard_id: str) -> list[ShotModel]:
        result = await self.session.execute(
            select(ShotModel)
            .where(ShotModel.storyboard_id == storyboard_id)
            .order_by(ShotModel.shot_number)
        )
        return list(result.scalars().all())


class AssetRepository:
    """Data access for assets."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs: Any) -> AssetModel:
        asset = AssetModel(asset_id=str(uuid.uuid4()), **kwargs)
        self.session.add(asset)
        return asset

    async def get(self, asset_id: str) -> AssetModel | None:
        result = await self.session.execute(
            select(AssetModel).where(AssetModel.asset_id == asset_id)
        )
        return result.scalar_one_or_none()

    async def find_by_project(self, project_id: str) -> list[AssetModel]:
        result = await self.session.execute(
            select(AssetModel).where(AssetModel.project_id == project_id)
        )
        return list(result.scalars().all())

    async def find_by_type(self, project_id: str, asset_type: str) -> list[AssetModel]:
        result = await self.session.execute(
            select(AssetModel).where(
                AssetModel.project_id == project_id,
                AssetModel.asset_type == asset_type,
            )
        )
        return list(result.scalars().all())


class JobRepository:
    """Data access for jobs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs: Any) -> JobModel:
        job = JobModel(job_id=str(uuid.uuid4()), **kwargs)
        self.session.add(job)
        return job

    async def get(self, job_id: str) -> JobModel | None:
        result = await self.session.execute(
            select(JobModel).where(JobModel.job_id == job_id)
        )
        return result.scalar_one_or_none()

    async def find_by_project(self, project_id: str) -> list[JobModel]:
        result = await self.session.execute(
            select(JobModel)
            .where(JobModel.project_id == project_id)
            .order_by(JobModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def find_by_status(self, status: str) -> list[JobModel]:
        result = await self.session.execute(
            select(JobModel).where(JobModel.status == status)
        )
        return list(result.scalars().all())


class ReviewRepository:
    """Data access for reviews."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs: Any) -> ReviewModel:
        review = ReviewModel(review_id=str(uuid.uuid4()), **kwargs)
        self.session.add(review)
        return review

    async def find_by_target(self, target_type: str, target_id: str) -> list[ReviewModel]:
        result = await self.session.execute(
            select(ReviewModel).where(
                ReviewModel.target_type == target_type,
                ReviewModel.target_id == target_id,
            )
        )
        return list(result.scalars().all())
