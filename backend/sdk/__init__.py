"""
Plugin SDK Exports (Part 18)

Re-export all public SDK symbols for plugin developers.
Plugin authors can import from `ai_manga_studio.sdk` to
access the complete SDK surface.
"""

from backend.plugins import (
    PluginBase,
    PluginManifest,
    PluginState,
    ExtensionPoint,
    PipelineStageExtension,
    AssetProcessingExtension,
    ExportFormatExtension,
    UIComponentExtension,
    ProviderExtension,
    PluginSDK,
)

__all__ = [
    "PluginBase",
    "PluginManifest",
    "PluginState",
    "ExtensionPoint",
    "PipelineStageExtension",
    "AssetProcessingExtension",
    "ExportFormatExtension",
    "UIComponentExtension",
    "ProviderExtension",
    "PluginSDK",
]
