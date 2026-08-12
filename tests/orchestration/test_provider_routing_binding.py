from __future__ import annotations

import pytest

from backend.orchestration.provider_binding import (
    resolve_or_reuse_provider_binding,
)
from backend.orchestration.repository import ProviderBindingConflictError
from backend.orchestration.schemas import ProviderBinding


class FakeBindingRepository:
    def __init__(self, binding: ProviderBinding | None = None):
        self.binding = binding
        self.get_calls = 0
        self.set_calls = 0

    def get_provider_binding(self, job_id: str) -> ProviderBinding | None:
        self.get_calls += 1
        return self.binding

    def set_provider_binding(
        self, job_id: str, binding: ProviderBinding
    ) -> ProviderBinding:
        self.set_calls += 1

        if self.binding is None:
            self.binding = binding
            return binding

        if self.binding != binding:
            raise ProviderBindingConflictError("binding conflict")

        return self.binding


def test_first_resolution_persists_binding():
    repository = FakeBindingRepository()
    resolver_calls = 0

    def resolver() -> ProviderBinding:
        nonlocal resolver_calls
        resolver_calls += 1
        return ProviderBinding(provider="h3", route="video")

    result = resolve_or_reuse_provider_binding(repository, "job-1", resolver)

    assert result.provider == "h3"
    assert resolver_calls == 1
    assert repository.get_calls == 1
    assert repository.set_calls == 1


def test_existing_binding_skips_resolver():
    repository = FakeBindingRepository(
        ProviderBinding(provider="h3", route="video")
    )
    resolver_calls = 0

    def resolver() -> ProviderBinding:
        nonlocal resolver_calls
        resolver_calls += 1
        return ProviderBinding(provider="wan", route="video")

    result = resolve_or_reuse_provider_binding(repository, "job-1", resolver)

    assert result.provider == "h3"
    assert resolver_calls == 0
    assert repository.get_calls == 1
    assert repository.set_calls == 0


def test_existing_binding_wins_when_default_provider_changes():
    repository = FakeBindingRepository()

    first = resolve_or_reuse_provider_binding(
        repository,
        "job-1",
        lambda: ProviderBinding(
            provider="h3", route="video", model="MiniMax-H3"
        ),
    )

    assert first.provider == "h3"

    resolver_calls = 0

    def changed_default() -> ProviderBinding:
        nonlocal resolver_calls
        resolver_calls += 1
        return ProviderBinding(
            provider="wan", route="video", model="wan2.2-ti2v-5b"
        )

    replayed = resolve_or_reuse_provider_binding(
        repository, "job-1", changed_default
    )

    assert replayed == first
    assert replayed.provider == "h3"
    assert resolver_calls == 0


def test_resolver_dict_is_validated():
    repository = FakeBindingRepository()

    result = resolve_or_reuse_provider_binding(
        repository,
        "job-1",
        lambda: {
            "provider": "h3",
            "route": "video",
            "model": "MiniMax-H3",
            "workflow": "h3/reference-video",
            "metadata": {"binding_version": 1},
        },
    )

    assert isinstance(result, ProviderBinding)
    assert result.provider == "h3"
    assert result.route == "video"
    assert result.model == "MiniMax-H3"


def test_binding_metadata_survives_reuse():
    expected = ProviderBinding(
        provider="h3",
        route="video",
        model="MiniMax-H3",
        workflow="h3/reference-video",
        metadata={"binding_version": 1, "account": "default"},
    )
    repository = FakeBindingRepository(expected)

    def resolver() -> ProviderBinding:
        raise AssertionError("resolver must not run for an already-bound job")

    result = resolve_or_reuse_provider_binding(repository, "job-1", resolver)

    assert result == expected


def test_repository_conflict_is_not_silently_swallowed():
    repository = FakeBindingRepository()

    def racing_resolver() -> ProviderBinding:
        repository.binding = ProviderBinding(provider="h3", route="video")
        return ProviderBinding(provider="wan", route="video")

    with pytest.raises(ProviderBindingConflictError):
        resolve_or_reuse_provider_binding(repository, "job-1", racing_resolver)
