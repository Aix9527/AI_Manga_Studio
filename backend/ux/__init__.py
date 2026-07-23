"""
Frontend UX Architecture — Creative workspace design (Part 26)

Defines the UX architecture for the AI Manga Studio frontend:
- Component hierarchy
- State management patterns
- Creative workspace layout
- Human review interfaces
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkspaceView(str, Enum):
    """Top-level workspace views."""
    DASHBOARD = "dashboard"
    PROJECT_EDITOR = "project_editor"
    CHARACTER_DESIGNER = "character_designer"
    STORYBOARD_EDITOR = "storyboard_editor"
    GENERATION_MONITOR = "generation_monitor"
    TIMELINE_EDITOR = "timeline_editor"
    ASSET_BROWSER = "asset_browser"
    SETTINGS = "settings"


class ReviewAction(str, Enum):
    """Human review actions."""
    APPROVE = "approve"
    REJECT = "reject"
    RETRY = "retry"
    MODIFY = "modify"


class EditorMode(str, Enum):
    """Editor interaction modes."""
    VIEW = "view"
    EDIT = "edit"
    REVIEW = "review"
    COMPARE = "compare"


@dataclass
class PanelConfig:
    """Configuration for a workspace panel."""
    panel_id: str
    title: str = ""
    width: int = 300
    height: int = 600
    collapsible: bool = True
    default_visible: bool = True
    icon: str = ""


@dataclass
class WorkspaceLayout:
    """Complete workspace layout definition."""
    layout_id: str = ""
    name: str = ""
    view: WorkspaceView = WorkspaceView.DASHBOARD
    panels: list[PanelConfig] = field(default_factory=list)
    default_right_panel_width: int = 400
    default_bottom_panel_height: int = 200


# ── UX Components ─────────────────────────────────────────────────────

@dataclass
class UXComponentSpec:
    """Specification for a frontend UI component."""
    component_name: str
    description: str = ""
    props: dict[str, str] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)
    slots: list[str] = field(default_factory=list)


# Define the core UX component tree
UX_COMPONENTS: list[UXComponentSpec] = [
    # Project views
    UXComponentSpec("ProjectDashboard", "Main project listing and creation",
                     {"projects": "Project[]", "onCreate": "() => void"}),
    UXComponentSpec("ProjectSettings", "Project configuration panel",
                     {"project": "Project", "onSave": "(Project) => void"}),

    # Character designer
    UXComponentSpec("CharacterDesigner", "Visual character creation and DNA editor",
                     {"character": "CharacterDNA", "mode": "EditorMode",
                      "onSave": "(CharacterDNA) => void", "onGenerate": "() => void"}),
    UXComponentSpec("CharacterGallery", "Browse all characters in a project",
                     {"characters": "CharacterDNA[]", "onSelect": "(id: string) => void"}),

    # Storyboard editor
    UXComponentSpec("StoryboardEditor", "Visual storyboard with drag-drop shot arrangement",
                     {"storyboard": "Storyboard", "onUpdate": "(Storyboard) => void"}),
    UXComponentSpec("ShotCard", "Individual shot display card",
                     {"shot": "Shot", "selected": "boolean", "onClick": "() => void"}),
    UXComponentSpec("ShotDetailPanel", "Detailed shot editor",
                     {"shot": "Shot", "onSave": "(Shot) => void",
                      "onRegenerate": "() => void"}),

    # Generation
    UXComponentSpec("GenerationMonitor", "Real-time generation progress dashboard",
                     {"jobs": "Job[]", "onCancel": "(jobId: string) => void"}),
    UXComponentSpec("GenerationQueue", "Queue of pending generation tasks",
                     {"tasks": "GenerationTask[]", "onReorder": "(tasks) => void"}),

    # Review
    UXComponentSpec("ReviewPanel", "Human review interface for AI-generated content",
                     {"target": "ReviewTarget", "onAction": "(action: ReviewAction, notes: string) => void"}),
    UXComponentSpec("ComparisonView", "Side-by-side before/after comparison",
                     {"original": "Asset", "generated": "Asset", "differences": "DiffResult"}),

    # Timeline
    UXComponentSpec("TimelineEditor", "Non-linear timeline for clip arrangement",
                     {"clips": "Clip[]", "audioTracks": "AudioTrack[]",
                      "playhead": "number", "onUpdate": "(Timeline) => void"}),
    UXComponentSpec("WaveformDisplay", "Audio waveform visualization",
                     {"audioPath": "string", "zoom": "number"}),

    # Asset browser
    UXComponentSpec("AssetBrowser", "Browse and manage project assets",
                     {"assets": "Asset[]", "filter": "AssetFilter",
                      "onImport": "(files: File[]) => void"}),
    UXComponentSpec("StyleSelector", "Visual style picker with previews",
                     {"styles": "StylePreset[]", "selected": "string",
                      "onSelect": "(styleId: string) => void"}),
]


# ── State Management ──────────────────────────────────────────────────

class UXStateManager:
    """
    Frontend state management architecture specification.

    Represents the expected state structure for the reactive frontend.
    """

    @staticmethod
    def get_initial_state() -> dict[str, Any]:
        """Return the initial application state shape."""
        return {
            "workspace": {
                "currentView": WorkspaceView.DASHBOARD.value,
                "activeLayout": "default",
                "panels": {
                    "rightPanel": {"visible": True, "activeTab": "properties"},
                    "bottomPanel": {"visible": False, "activeTab": "console"},
                    "leftPanel": {"visible": True, "activeTab": "assets"},
                },
            },
            "project": {
                "currentProjectId": None,
                "projects": [],
                "isDirty": False,
            },
            "generation": {
                "queue": [],
                "activeJobs": [],
                "completedJobs": [],
                "isGenerating": False,
            },
            "review": {
                "pendingReviews": [],
                "currentReview": None,
            },
            "selection": {
                "selectedShotId": None,
                "selectedCharacterId": None,
                "selectedAssetId": None,
            },
        }


# ── Workspace Presets ─────────────────────────────────────────────────

WORKSPACE_PRESETS: list[WorkspaceLayout] = [
    WorkspaceLayout(
        layout_id="storyboard_default",
        name="Storyboard Workspace",
        view=WorkspaceView.STORYBOARD_EDITOR,
        panels=[
            PanelConfig("shot_list", "Shots", default_visible=True),
            PanelConfig("shot_properties", "Shot Properties", width=350),
            PanelConfig("asset_browser", "Assets", default_visible=True),
            PanelConfig("preview", "Preview", width=640, height=360),
        ],
    ),
    WorkspaceLayout(
        layout_id="character_default",
        name="Character Designer",
        view=WorkspaceView.CHARACTER_DESIGNER,
        panels=[
            PanelConfig("character_list", "Characters"),
            PanelConfig("dna_editor", "DNA Editor", width=400),
            PanelConfig("reference_preview", "Reference", width=512, height=512),
        ],
    ),
    WorkspaceLayout(
        layout_id="timeline_default",
        name="Timeline & Compositing",
        view=WorkspaceView.TIMELINE_EDITOR,
        panels=[
            PanelConfig("timeline_tracks", "Timeline"),
            PanelConfig("preview", "Preview", width=640, height=360),
            PanelConfig("properties", "Clip Properties", width=300),
            PanelConfig("tools", "Tools"),
        ],
        default_bottom_panel_height=250,
    ),
]
