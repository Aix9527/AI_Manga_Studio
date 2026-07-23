"""
Provider Registry — Plugin-contributed providers (Part 18)

Tracks custom AI providers (LLM, Image, Video, Audio) registered
by plugins. Each provider implements the corresponding base provider
interface.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Registry for custom providers contributed by plugins."""

    def __init__(self) -> None:
        self._providers: dict[str, Any] = {}  # provider_id -> provider instance
        self._plugin_owners: dict[str, str] = {}  # provider_id -> plugin_id
        self._by_type: dict[str, list[str]] = {}  # provider_type -> [provider_id, ...]

    def register(
        self,
        provider_id: str,
        provider_instance: Any,
        plugin_id: str,
        provider_type: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a custom provider."""
        if provider_id in self._providers:
            logger.warning(f"Provider '{provider_id}' already registered, overwriting")
        self._providers[provider_id] = provider_instance
        self._plugin_owners[provider_id] = plugin_id
        if provider_type:
            self._by_type.setdefault(provider_type, []).append(provider_id)

    def unregister(self, provider_id: str) -> bool:
        if provider_id not in self._providers:
            return False
        del self._providers[provider_id]
        self._plugin_owners.pop(provider_id, None)
        for type_list in self._by_type.values():
            if provider_id in type_list:
                type_list.remove(provider_id)
        return True

    def unregister_all_for_plugin(self, plugin_id: str) -> int:
        owned = [pid for pid, oid in self._plugin_owners.items() if oid == plugin_id]
        for pid in owned:
            self.unregister(pid)
        return len(owned)

    def get(self, provider_id: str) -> Any | None:
        return self._providers.get(provider_id)

    def list_by_type(self, provider_type: str) -> list[str]:
        return list(self._by_type.get(provider_type, []))

    def list_all(self) -> list[str]:
        return list(self._providers.keys())
