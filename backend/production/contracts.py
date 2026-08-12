from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from backend.orchestration.schemas import ProviderBinding


@dataclass(frozen=True)
class ProductionExecutionRequest:
    job_id: str
    project_id: str
    stage_key: str
    provider_binding: ProviderBinding
    settings: dict[str, Any]


@dataclass(frozen=True)
class ProductionExecutionResult:
    artifacts: list[dict[str, Any]]
    metadata: dict[str, Any]


class ProductionExecutionPort(Protocol):
    def execute(
        self,
        request: ProductionExecutionRequest,
    ) -> ProductionExecutionResult:
        ...

    def cancel(
        self,
        job_id: str,
    ) -> bool:
        ...
