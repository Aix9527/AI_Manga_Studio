"""
Plugin Capability — Capability model and declaration (Part 18)

Each plugin exposes one or more capabilities. A capability is the atomic
unit of extensibility — it defines what the plugin contributes to the
platform (an agent, a provider, a workflow node, etc.).

Nine capability types:
    agent, provider, workflow_node, media_processor,
    exporter, importer, ui_panel, event_handler, validator
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CapabilityType(str, Enum):
    """Standard capability types."""
    AGENT = "agent"
    PROVIDER = "provider"
    WORKFLOW_NODE = "workflow_node"
    MEDIA_PROCESSOR = "media_processor"
    EXPORTER = "exporter"
    IMPORTER = "importer"
    UI_PANEL = "ui_panel"
    EVENT_HANDLER = "event_handler"
    VALIDATOR = "validator"


@dataclass
class Capability:
    """A pluggable capability contributed by a plugin."""

    capability_type: str
    capability_id: str
    name: str
    version: str
    plugin_id: str = ""
    description: str = ""

    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None

    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def matches(self, cap_type: str | None = None, cap_id: str | None = None) -> bool:
        """Check if this capability matches type/id filters."""
        if cap_type and self.capability_type != cap_type:
            return False
        if cap_id and self.capability_id != cap_id:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_type": self.capability_type,
            "capability_id": self.capability_id,
            "name": self.name,
            "version": self.version,
            "plugin_id": self.plugin_id,
            "enabled": self.enabled,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "metadata": self.metadata,
        }


@dataclass
class CapabilityHealth:
    """Health status of an active capability."""

    capability_id: str
    plugin_id: str
    healthy: bool = True
    error_message: str = ""
    last_heartbeat: float = 0.0
    response_time_ms: float = 0.0


class CapabilityConflictError(Exception):
    """Raised when two plugins register the same capability_id."""

    def __init__(self, capability_id: str, existing_plugin: str, new_plugin: str) -> None:
        super().__init__(
            f"Capability conflict: '{capability_id}' already registered "
            f"by '{existing_plugin}', cannot be re-registered by '{new_plugin}'"
        )
