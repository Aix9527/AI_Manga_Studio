"""
Agent Registry — Plugin-contributed agents (Part 18)

Tracks custom agents registered by plugins. Each agent is an instance
or factory that extends the BaseAgent protocol.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Registry for custom agents contributed by plugins."""

    def __init__(self) -> None:
        self._agents: dict[str, Any] = {}  # agent_id -> agent instance/factory
        self._plugin_owners: dict[str, str] = {}  # agent_id -> plugin_id
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(
        self,
        agent_id: str,
        agent_factory: Any,
        plugin_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a custom agent."""
        if agent_id in self._agents:
            logger.warning(f"Agent '{agent_id}' already registered, overwriting")
        self._agents[agent_id] = agent_factory
        self._plugin_owners[agent_id] = plugin_id
        self._metadata[agent_id] = metadata or {}
        logger.info(f"Agent '{agent_id}' registered by plugin '{plugin_id}'")

    def unregister(self, agent_id: str) -> bool:
        if agent_id not in self._agents:
            return False
        del self._agents[agent_id]
        self._plugin_owners.pop(agent_id, None)
        self._metadata.pop(agent_id, None)
        return True

    def unregister_all_for_plugin(self, plugin_id: str) -> int:
        owned = [aid for aid, pid in self._plugin_owners.items() if pid == plugin_id]
        for aid in owned:
            self.unregister(aid)
        return len(owned)

    def get(self, agent_id: str) -> Any | None:
        return self._agents.get(agent_id)

    def list_all(self) -> list[str]:
        return list(self._agents.keys())

    def is_registered(self, agent_id: str) -> bool:
        return agent_id in self._agents
