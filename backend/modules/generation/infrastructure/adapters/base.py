
"""Base provider contract for generation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    purpose: str
    prompt: str
    parameters: dict[str, Any]
    references: list[str]


@dataclass
class ProviderResult:
    remote_task_id: str
    status: str
    outputs: list[dict[str, Any]]
    metadata: dict[str, Any]


class GenerationProvider(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str:
        ...

    @abstractmethod
    async def submit(self, request: ProviderRequest) -> ProviderResult:
        ...

    @abstractmethod
    async def status(self, remote_task_id: str) -> ProviderResult:
        ...

    @abstractmethod
    async def cancel(self, remote_task_id: str) -> bool:
        ...

    @abstractmethod
    async def reconcile(self, remote_task_id: str) -> ProviderResult:
        ...

    @abstractmethod
    async def health(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def capabilities(self) -> list[str]:
        ...
