from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from backend.orchestration.schemas import ProviderBinding


class ProviderBindingRepository(Protocol):
    def get_provider_binding(
        self,
        job_id: str,
    ) -> ProviderBinding | None:
        ...

    def set_provider_binding(
        self,
        job_id: str,
        binding: ProviderBinding,
    ) -> ProviderBinding:
        ...


ProviderResolver = Callable[
    [],
    ProviderBinding | dict[str, Any],
]


def resolve_or_reuse_provider_binding(
    repository: ProviderBindingRepository,
    job_id: str,
    resolver: ProviderResolver,
) -> ProviderBinding:
    """
    Resolve a provider exactly once for a durable job.

    If a persisted binding already exists, it is returned without invoking the
    resolver. Otherwise the resolver chooses a candidate and the repository
    atomically persists it using first-write-wins semantics.

    Repository arbitration remains authoritative if multiple processes race to
    establish the first binding.
    """

    existing = repository.get_provider_binding(job_id)

    if existing is not None:
        return existing

    candidate = resolver()

    if not isinstance(candidate, ProviderBinding):
        candidate = ProviderBinding.model_validate(candidate)

    return repository.set_provider_binding(
        job_id,
        candidate,
    )
