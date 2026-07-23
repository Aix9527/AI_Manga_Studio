
"""Project repository implementation."""


from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.modules.projects.domain.project import Project
from backend.modules.projects.infrastructure.models import ProjectModel
from backend.shared.errors import NotFoundError, RevisionConflictError
from backend.shared.infrastructure.database.pagination import PageRequest, PageResult, encode_cursor


class SqlAlchemyProjectRepository:
    """SQLAlchemy implementation of Project persistence."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, project: Project) -> None:
        model = ProjectModel(
            id=project.project_id,
            title=project.title,
            description=project.description,
            status=project.status,
            settings_json=project.settings_json,
            created_at=project.created_at,
            updated_at=project.updated_at,
            revision=project.revision,
        )
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()

    async def get(self, project_id: str) -> Project:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ProjectModel).where(ProjectModel.id == project_id)
            )
            model = result.scalar_one_or_none()
            if model is None:
                raise NotFoundError("Project", project_id)
            return self._to_domain(model)

    async def list_recent(self, page: PageRequest) -> PageResult[Project]:
        async with self._session_factory() as session:
            query = (
                select(ProjectModel)
                .order_by(ProjectModel.created_at.desc(), ProjectModel.id)
                .limit(page.limit + 1)
            )
            result = await session.execute(query)
            models = result.scalars().all()

            has_more = len(models) > page.limit
            items = models[:page.limit]

            next_cursor = None
            if has_more:
                last = items[-1]
                next_cursor = encode_cursor(last.created_at, last.id)

            return PageResult(
                items=[self._to_domain(m) for m in items],
                next_cursor=next_cursor,
            )

    async def save_with_optimistic_lock(
        self, project: Project, expected_revision: int
    ) -> None:
        async with self._session_factory() as session:
            result = await session.execute(
                update(ProjectModel)
                .where(
                    ProjectModel.id == project.project_id,
                    ProjectModel.revision == expected_revision,
                )
                .values(
                    title=project.title,
                    description=project.description,
                    status=project.status,
                    settings_json=project.settings_json,
                    updated_at=project.updated_at,
                    revision=project.revision,
                )
            )
            if result.rowcount == 0:
                raise RevisionConflictError(
                    "Project", project.project_id, expected_revision
                )
            await session.commit()

    @staticmethod
    def _to_domain(model: ProjectModel) -> Project:
        return Project(
            project_id=model.id,
            title=model.title,
            description=model.description,
            status=model.status,
            settings_json=model.settings_json,
            created_at=model.created_at,
            updated_at=model.updated_at,
            revision=model.revision,
        )
