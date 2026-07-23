"""Provider registry tests."""

import pytest

from backend.modules.generation.infrastructure.adapters.fake.adapter import (
    FakeImageProvider,
)
from backend.modules.generation.infrastructure.provider_registry import (
    InMemoryProviderRegistry,
)


def test_provider_can_be_registered_and_resolved() -> None:
    registry = InMemoryProviderRegistry()
    provider = FakeImageProvider()

    registry.register("fake-image", provider)

    assert registry.get("fake-image") is provider
    assert registry.providers() == ["fake-image"]


def test_duplicate_provider_is_rejected() -> None:
    registry = InMemoryProviderRegistry()
    provider = FakeImageProvider()

    registry.register("fake-image", provider)

    with pytest.raises(ValueError, match="already registered"):
        registry.register("fake-image", provider)


def test_missing_provider_raises_clear_error() -> None:
    registry = InMemoryProviderRegistry()

    with pytest.raises(KeyError, match="not found"):
        registry.get("missing")
