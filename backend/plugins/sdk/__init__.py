"""
Plugin SDK — Extension base classes for third-party developers (Part 18)

Each SDK module provides the abstract base class that plugin developers
must subclass to extend the platform.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


# ── Agent Plugin SDK ──────────────────────────────────────────────────

class AgentPlugin(ABC):
    """Base class for agent plugins."""

    @abstractmethod
    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the agent's core logic."""
        ...

    @abstractmethod
    def get_metadata(self) -> dict[str, Any]:
        """Return agent metadata (name, version, description)."""
        ...

    async def validate(self, inputs: dict[str, Any]) -> None:
        """Optional: validate inputs before execution."""
        pass

    async def on_error(self, error: Exception, inputs: dict[str, Any]) -> dict[str, Any]:
        """Optional: handle errors gracefully."""
        return {"error": str(error)}


# ── Provider Plugin SDK ───────────────────────────────────────────────

class ProviderPlugin(ABC):
    """Base class for provider plugins (LLM, Image, Video, Audio)."""

    @abstractmethod
    async def invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        """Invoke the provider with a request."""
        ...

    @abstractmethod
    def get_provider_type(self) -> str:
        """Return the provider type (llm, image, video, audio)."""
        ...

    @abstractmethod
    def get_metadata(self) -> dict[str, Any]:
        """Return provider metadata."""
        ...

    async def health_check(self) -> bool:
        """Optional: check provider health."""
        return True

    async def get_usage(self) -> dict[str, Any]:
        """Optional: return usage/cost stats."""
        return {}


# ── Workflow Node Plugin SDK ──────────────────────────────────────────

class WorkflowNodePlugin(ABC):
    """Base class for custom workflow node plugins."""

    @abstractmethod
    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the node's logic."""
        ...

    @abstractmethod
    def get_node_type(self) -> str:
        """Return the unique node type identifier."""
        ...

    def get_input_schema(self) -> dict[str, Any] | None:
        """Optional: JSON Schema for inputs."""
        return None

    def get_output_schema(self) -> dict[str, Any] | None:
        """Optional: JSON Schema for outputs."""
        return None


# ── Media Processor Plugin SDK ────────────────────────────────────────

class MediaProcessorPlugin(ABC):
    """Base class for media processing plugins (image/video/audio filters)."""

    @abstractmethod
    async def process(self, asset_path: str, params: dict[str, Any]) -> str:
        """Process an asset and return the output path."""
        ...

    @abstractmethod
    def supported_formats(self) -> list[str]:
        """Return list of supported input formats."""
        ...


# ── Exporter Plugin SDK ───────────────────────────────────────────────

class ExporterPlugin(ABC):
    """Base class for exporter plugins."""

    @abstractmethod
    async def export(self, project_data: dict[str, Any], output_path: str) -> str:
        """Export project data to output path. Returns the output path."""
        ...

    @abstractmethod
    def get_format_name(self) -> str:
        """Return the export format name (e.g., 'mp4', 'pdf', 'otio')."""
        return "unknown"


# ── Importer Plugin SDK ───────────────────────────────────────────────

class ImporterPlugin(ABC):
    """Base class for importer plugins."""

    @abstractmethod
    async def import_data(self, source_path: str) -> dict[str, Any]:
        """Import data from source path. Returns project-compatible dict."""
        ...

    @abstractmethod
    def supported_formats(self) -> list[str]:
        """Return list of supported input formats."""
        ...


# ── Event Handler Plugin SDK ──────────────────────────────────────────

class EventHandlerPlugin(ABC):
    """Base class for event handler / automation hook plugins."""

    @abstractmethod
    async def handle(self, event_type: str, payload: dict[str, Any]) -> None:
        """Handle an event."""
        ...

    @abstractmethod
    def subscribed_events(self) -> list[str]:
        """Return list of event types this handler subscribes to."""
        ...


# ── UI Plugin SDK ─────────────────────────────────────────────────────

class UIPlugin(ABC):
    """Base class for UI extension plugins."""

    @abstractmethod
    def get_ui_manifest(self) -> dict[str, Any]:
        """Return the UI manifest (panels, widgets, routes)."""
        ...

    def get_assets(self) -> dict[str, str]:
        """Return mapping of asset_name -> asset_path."""
        return {}
