
"""Projects module public API."""

from dataclasses import dataclass

from backend.modules.projects.application.handlers import CreateProjectHandler
from backend.modules.projects.infrastructure.repository import SqlAlchemyProjectRepository
from backend.shared.ids import IdGenerator
from backend.shared.time import Clock


@dataclass(slots=True)
class ProjectsModuleApi:
    project_repo: SqlAlchemyProjectRepository
    id_generator: IdGenerator
    clock: Clock

    @property
    def _project_repo(self) -> SqlAlchemyProjectRepository:
        return self.project_repo

    @property
    def _create_project_handler(self) -> CreateProjectHandler:
        return CreateProjectHandler(self.project_repo, self.id_generator, self.clock)
