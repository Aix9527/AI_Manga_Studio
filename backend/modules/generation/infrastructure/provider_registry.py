
"""In-memory provider registry for generation."""

from dataclasses import dataclass

from backend.modules.generation.infrastructure.adapters.base import GenerationProvider


@dataclass(slots=True)
class InMemoryProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, GenerationProvider] = {}

    def register(self, provider_id: str, provider: GenerationProvider) -> None:
        if provider_id in self._providers:
            raise ValueError(f"Provider '{provider_id}' is already registered.")
        self._providers[provider_id] = provider

    def get(self, provider_id: str) -> GenerationProvider:
        try:
            return self._providers[provider_id]
        except KeyError:
            raise KeyError(f"Provider '{provider_id}' not found. Available: {list(self._providers.keys())}")

    def providers(self) -> list[str]:
        return list(self._providers.keys())

    def find_providers(self, capability: str) -> list[str]:
        return [pid for pid, p in self._providers.items() if capability in p.capabilities()]
