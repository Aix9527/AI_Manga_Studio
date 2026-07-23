"""
Repository Pattern — Data Access Layer (Part 13)

Generic async repositories with common CRUD operations,
pagination, filtering, and Unit of Work pattern support.
All queries go through repositories, not raw SQLAlchemy.
"""

from __future__ import annotations

from typing import Any, Generic, Optional, Type, TypeVar
from uuid import uuid4

from sqlalchemy import func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from backend.database.models import (
    Project,
    Story,
    Character,
    Scene,
    Storyboard,
    Shot,
    Asset,
    Job,
    Review,
    MemoryRecord,
    ProviderConfig,
)


T = TypeVar("T", bound=DeclarativeBase)


class BaseRepository(Generic[T]):
    """Generic async repository with standard CRUD operations."""

    def __init__(self, session: AsyncSession, model: Type[T]) -> None:
        self.session = session
        self.model = model

    async def get(self, id: str) -> Optional[T]:
        """Get entity by primary key."""
        result = await self.session.execute(
            select(self.model).where(
                getattr(self.model, self._pk_column()) == id
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        offset: int = 0,
        limit: int = 100,
        **filters: Any,
    ) -> list[T]:
        """List entities with optional filters."""
        stmt = select(self.model)
        for key, value in filters.items():
            col = getattr(self.model, key)
            stmt = stmt.where(col == value)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, **filters: Any) -> int:
        """Count entities matching filters."""
        stmt = select(func.count()).select_from(self.model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def create(self, **kwargs: Any) -> T:
        """Create and persist a new entity."""
        entity = self.model(**kwargs)
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, id: str, **kwargs: Any) -> Optional[T]:
        """Update an existing entity."""
        entity = await self.get(id)
        if not entity:
            return None
        for key, value in kwargs.items():
            setattr(entity, key, value)
        await self.session.flush()
        return entity

    async def delete(self, id: str) -> bool:
        """Soft-delete an entity."""
        entity = await self.get(id)
        if not entity:
            return False
        setattr(entity, "is_deleted", True)
        await self.session.flush()
        return True

    async def hard_delete(self, id: str) -> bool:
        """Permanently delete an entity."""
        pk = self._pk_column()
        stmt = delete(self.model).where(getattr(self.model, pk) == id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    def _pk_column(self) -> str:
        """Return the primary key column name for this model."""
        # Convention: model_name_id  (e.g., project_id for Project)
        return f"{self.model.__tablename__.rstrip('s')}_id"


# ── Concrete Repositories ───────────────────────────────────────────────


class ProjectRepository(BaseRepository[Project]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Project)

    async def find_active(self) -> list[Project]:
        """Find all non-deleted projects."""
        return await self.list(is_deleted=False)


class StoryRepository(BaseRepository[Story]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Story)

    async def find_by_project(self, project_id: str) -> list[Story]:
        return await self.list(project_id=project_id, is_deleted=False)


class CharacterRepository(BaseRepository[Character]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Character)

    async def find_by_project(self, project_id: str) -> list[Character]:
        return await self.list(project_id=project_id, is_deleted=False)

    async def find_by_name(
        self, project_id: str, name: str
    ) -> Optional[Character]:
        result = await self.session.execute(
            select(Character).where(
                Character.project_id == project_id,
                Character.name == name,
                Character.is_deleted == False,
            )
        )
        return result.scalar_one_or_none()


class SceneRepository(BaseRepository[Scene]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Scene)

    async def find_by_project(self, project_id: str) -> list[Scene]:
        return await self.list(
            project_id=project_id, is_deleted=False
        )


class StoryboardRepository(BaseRepository[Storyboard]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Storyboard)

    async def find_by_project(self, project_id: str) -> list[Storyboard]:
        return await self.list(project_id=project_id, is_deleted=False)


class ShotRepository(BaseRepository[Shot]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Shot)

    async def find_by_storyboard(self, storyboard_id: str) -> list[Shot]:
        return await self.list(storyboard_id=storyboard_id)


class AssetRepository(BaseRepository[Asset]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Asset)

    async def find_by_project(self, project_id: str) -> list[Asset]:
        return await self.list(project_id=project_id, is_deleted=False)

    async def find_by_type(
        self, project_id: str, asset_type: str
    ) -> list[Asset]:
        return await self.list(
            project_id=project_id,
            asset_type=asset_type,
            is_deleted=False,
        )


class JobRepository(BaseRepository[Job]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Job)

    async def find_by_project(self, project_id: str) -> list[Job]:
        return await self.list(project_id=project_id)

    async def find_by_status(self, status: str) -> list[Job]:
        return await self.list(status=status)


class ReviewRepository(BaseRepository[Review]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Review)

    async def find_by_target(
        self, target_type: str, target_id: str
    ) -> list[Review]:
        return await self.list(target_type=target_type, target_id=target_id)


class MemoryRecordRepository(BaseRepository[MemoryRecord]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MemoryRecord)

    async def find_by_key(
        self, project_id: str, key: str
    ) -> list[MemoryRecord]:
        return await self.list(project_id=project_id, key=key)


class ProviderConfigRepository(BaseRepository[ProviderConfig]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ProviderConfig)

    async def find_enabled(self, provider_type: str) -> list[ProviderConfig]:
        return await self.list(
            provider_type=provider_type, is_enabled=True
        )


# ── Unit of Work ────────────────────────────────────────────────────────


class UnitOfWork:
    """
    Coordinates persistence of multiple repositories in a single transaction.

    Usage:
        async with uow:
            project = await uow.projects.create(name="My Manga")
            await uow.commit()
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.stories = StoryRepository(session)
        self.characters = CharacterRepository(session)
        self.scenes = SceneRepository(session)
        self.storyboards = StoryboardRepository(session)
        self.shots = ShotRepository(session)
        self.assets = AssetRepository(session)
        self.jobs = JobRepository(session)
        self.reviews = ReviewRepository(session)
        self.memory = MemoryRecordRepository(session)
        self.providers = ProviderConfigRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def __aenter__(self) -> "UnitOfWork":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.session.close()
