"""
Node Registry — Workflow node registration from plugins (Part 18)

Plugins can contribute custom workflow nodes. This registry tracks
node type registrations and provides type-safe node creation.

Node types registered here extend the NODE_REGISTRY from workflow.nodes.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NodeRegistry:
    """Registry for custom workflow node types registered by plugins."""

    def __init__(self) -> None:
        self._nodes: dict[str, type] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self._plugin_owners: dict[str, str] = {}  # node_type -> plugin_id

    def register(
        self,
        node_type: str,
        node_cls: type,
        plugin_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a custom workflow node type."""
        if node_type in self._nodes:
            logger.warning(
                f"Node type '{node_type}' already registered. "
                f"Overwriting with plugin '{plugin_id}'"
            )
        self._nodes[node_type] = node_cls
        self._plugin_owners[node_type] = plugin_id
        self._metadata[node_type] = metadata or {}
        logger.info(f"Node type '{node_type}' registered by plugin '{plugin_id}'")

    def unregister(self, node_type: str) -> bool:
        """Remove a node type registration."""
        if node_type not in self._nodes:
            return False
        del self._nodes[node_type]
        self._plugin_owners.pop(node_type, None)
        self._metadata.pop(node_type, None)
        return True

    def unregister_all_for_plugin(self, plugin_id: str) -> int:
        owned = [nt for nt, pid in self._plugin_owners.items() if pid == plugin_id]
        for nt in owned:
            self.unregister(nt)
        return len(owned)

    def get(self, node_type: str) -> type | None:
        return self._nodes.get(node_type)

    def list_all(self) -> dict[str, str]:
        """Return {node_type: plugin_id} mapping."""
        return dict(self._plugin_owners)

    def is_registered(self, node_type: str) -> bool:
        return node_type in self._nodes

    def merge_into_global_registry(self, global_registry: dict[str, type]) -> dict[str, type]:
        """Merge plugin nodes into the global NODE_REGISTRY, returning merged copy."""
        merged = dict(global_registry)
        merged.update(self._nodes)
        return merged
