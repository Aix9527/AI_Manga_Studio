
"""Application handlers for Projects."""


from backend.modules.projects.application.commands import CreateProjectCommand
from backend.modules.projects.domain.project import Project
from backend.modules.projects.infrastructure.repository import SqlAlchemyProjectRepository
from backend.shared.ids import IdGenerator
from backend.shared.time import Clock


class CreateProjectHandler:
    def __init__(
        self,
        repo: SqlAlchemyProjectRepository,
        id_generator: IdGenerator,
        clock: Clock,
    ) -> None:
        self._repo = repo
        self._id_generator = id_generator
        self._clock = clock

    async def handle(self, cmd: CreateProjectCommand) -> Project:
        now = self._clock.now()
        project = Project(
            project_id=self._id_generator.new("proj"),
            title=cmd.title,
            description=cmd.description,
            created_at=now,
            updated_at=now,
        )
        await self._repo.add(project)
        return project
