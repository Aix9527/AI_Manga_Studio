
"""Workflows module public API."""

from dataclasses import dataclass

from backend.modules.workflows.infrastructure.repository import SqlAlchemyJobRepository
from backend.shared.ids import IdGenerator
from backend.shared.time import Clock


@dataclass(slots=True)
class WorkflowsModuleApi:
    job_repo: SqlAlchemyJobRepository
    id_generator: IdGenerator
    clock: Clock

    @property
    def _job_repo(self) -> SqlAlchemyJobRepository:
        return self.job_repo
