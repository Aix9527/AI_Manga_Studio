"""Director Provider Registry (Phase 12.7-B, GPT spec).

Unified registry managing the five director providers::

    OpenAI GPT | Claude | Qwen | DeepSeek | Rule

- providers are lazily constructed from environment keys (silently
  unavailable when a key is missing, so the dispatcher falls back)
- ``get(name)`` / ``available()`` / ``names()`` give the dispatcher and the
  real arena runner a single place to resolve providers
- tests inject fake providers through ``register(name, provider)``
"""

from __future__ import annotations

from threading import Lock
from typing import Any

from backend.director.providers.base import DirectorProvider
from backend.director.providers.claude_provider import ClaudeDirectorProvider
from backend.director.providers.openai_provider import OpenAIDirectorProvider
from backend.director.providers.deepseek_provider import DeepSeekDirectorProvider
from backend.director.providers.qwen_provider import QwenDirectorProvider
from backend.director.providers.rule_provider import RuleDirectorProvider

# registry name -> provider class factory (lazy, env-key aware)
DEFAULT_FACTORIES: dict[str, Any] = {
    "rule-v2": lambda: RuleDirectorProvider(),
    "llm-gpt": lambda: OpenAIDirectorProvider(),
    "llm-claude": lambda: ClaudeDirectorProvider(),
    "llm-qwen": lambda: QwenDirectorProvider(),
    "llm-deepseek": lambda: DeepSeekDirectorProvider(),
}


class DirectorProviderRegistry:
    """Single registry for all director providers (Phase 12.7-B)."""

    def __init__(self, factories: dict[str, Any] | None = None):
        self._factories = dict(factories or DEFAULT_FACTORIES)
        self._providers: dict[str, DirectorProvider] = {}
        self._lock = Lock()

    # ------------------------------------------------------------ access
    def names(self) -> list[str]:
        return sorted(self._factories)

    def get(self, name: str) -> DirectorProvider:
        """Return the cached provider for ``name`` (constructing if needed)."""
        with self._lock:
            if name not in self._factories:
                raise KeyError(f"no provider factory for {name!r}")
            if name not in self._providers:
                self._providers[name] = self._factories[name]()
            return self._providers[name]

    def available(self) -> list[str]:
        """Providers whose API key / runtime is ready right now."""
        out: list[str] = []
        for name in self.names():
            try:
                provider = self.get(name)
            except Exception:  # noqa: BLE001 - never crash the registry
                continue
            if getattr(provider, "is_available", True):
                out.append(name)
        return out

    def register(self, name: str, provider: DirectorProvider) -> None:
        """Test hook / custom wiring: pin an explicit provider instance."""
        with self._lock:
            self._factories[name] = lambda: provider
            self._providers[name] = provider

    def unregister(self, name: str) -> None:
        with self._lock:
            self._factories.pop(name, None)
            self._providers.pop(name, None)

    def summary(self) -> dict:
        return {
            "registered": self.names(),
            "available": self.available(),
            "count": len(self.names()),
        }
