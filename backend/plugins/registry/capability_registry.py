"""
Capability Registry — Capability registration and resolution (Part 18)

Manages all capabilities exposed by plugins. Provides typed lookups
for agents, providers, workflow nodes, media processors, etc.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from backend.plugins.domain.capability import (
    Capability, CapabilityHealth, CapabilityType, CapabilityConflictError,
)

logger = logging.getLogger(__name__)


class CapabilityRegistry:
    """Registry of all plugin Capabilities, indexed by type and ID."""

    def __init__(self) -> None:
        self._by_id: dict[str, Capability] = {}
        self._by_type: dict[str, list[str]] = defaultdict(list)
        self._by_plugin: dict[str, list[str]] = defaultdict(list)
        self._health: dict[str, CapabilityHealth] = {}

    def register(self, capability: Capability) -> None:
        """Register a capability. Raises if ID conflict."""
        if capability.capability_id in self._by_id:
            existing = self._by_id[capability.capability_id]
            if existing.plugin_id != capability.plugin_id:
                raise CapabilityConflictError(
                    capability.capability_id, existing.plugin_id, capability.plugin_id,
                )
            # Same plugin — allow update
            logger.debug(f"Updating capability: {capability.capability_id}")

        self._by_id[capability.capability_id] = capability
        self._by_type[capability.capability_type].append(capability.capability_id)
        self._by_plugin[capability.plugin_id].append(capability.capability_id)

        # Initialize health
        if capability.capability_id not in self._health:
            self._health[capability.capability_id] = CapabilityHealth(
                capability_id=capability.capability_id,
                plugin_id=capability.plugin_id,
            )

    def unregister(self, capability_id: str) -> bool:
        """Remove a capability."""
        cap = self._by_id.pop(capability_id, None)
        if not cap:
            return False

        self._by_type[cap.capability_type].remove(capability_id)
        self._by_plugin[cap.plugin_id].remove(capability_id)
        self._health.pop(capability_id, None)
        return True

    def unregister_all_for_plugin(self, plugin_id: str) -> int:
        """Remove all capabilities for a plugin. Returns count removed."""
        cap_ids = list(self._by_plugin.get(plugin_id, []))
        for cid in cap_ids:
            self.unregister(cid)
        return len(cap_ids)

    # ── Queries ───────────────────────────────────────────────────────

    def get(self, capability_id: str) -> Capability | None:
        return self._by_id.get(capability_id)

    def list_by_type(self, cap_type: str) -> list[Capability]:
        ids = self._by_type.get(cap_type, [])
        return [self._by_id[i] for i in ids if i in self._by_id]

    def list_for_plugin(self, plugin_id: str) -> list[Capability]:
        ids = self._by_plugin.get(plugin_id, [])
        return [self._by_id[i] for i in ids if i in self._by_id]

    def list_agents(self) -> list[Capability]:
        return self.list_by_type(CapabilityType.AGENT.value)

    def list_providers(self) -> list[Capability]:
        return self.list_by_type(CapabilityType.PROVIDER.value)

    def list_workflow_nodes(self) -> list[Capability]:
        return self.list_by_type(CapabilityType.WORKFLOW_NODE.value)

    def list_media_processors(self) -> list[Capability]:
        return self.list_by_type(CapabilityType.MEDIA_PROCESSOR.value)

    def list_exporters(self) -> list[Capability]:
        return self.list_by_type(CapabilityType.EXPORTER.value)

    # ── Health ────────────────────────────────────────────────────────

    def update_health(self, capability_id: str, healthy: bool, error: str = "",
                      response_time_ms: float = 0.0) -> None:
        import time
        if capability_id in self._health:
            self._health[capability_id].healthy = healthy
            self._health[capability_id].error_message = error
            self._health[capability_id].response_time_ms = response_time_ms
            self._health[capability_id].last_heartbeat = time.time()

    def get_health(self, capability_id: str) -> CapabilityHealth | None:
        return self._health.get(capability_id)

    def list_unhealthy(self) -> list[CapabilityHealth]:
        return [h for h in self._health.values() if not h.healthy]

    # ── Stats ─────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        return {
            "total_capabilities": len(self._by_id),
            "by_type": {t: len(ids) for t, ids in self._by_type.items()},
            "healthy_count": sum(1 for h in self._health.values() if h.healthy),
            "unhealthy_count": sum(1 for h in self._health.values() if not h.healthy),
        }
