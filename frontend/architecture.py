"""
Frontend Architecture — Component & Page Structure (Part 15)

React 18 + TypeScript + Zustand + React Router v6
with Ant Design (antd) component library.

Directory structure:
frontend/
  public/              Static assets
  src/
    components/        Shared UI components
    pages/             Route-level page components
    store/             Zustand state management
    hooks/             Custom React hooks
    services/          API client layer
    types/             TypeScript type definitions
    utils/             Utility functions
    App.tsx            Root component
    main.tsx           Entry point
"""

# This file serves as the frontend architecture definition document.
# The actual frontend code would be in React/TypeScript.
# Below is a structural overview and component tree.

FRONTEND_ARCHITECTURE = {
    "framework": "React 18",
    "language": "TypeScript",
    "bundler": "Vite",
    "state": "Zustand",
    "router": "React Router v6",
    "ui_library": "Ant Design (antd)",
    "http_client": "Axios",
    "websocket": "Native WebSocket API",
    "auth": "JWT (token-based)",
}

ROUTES = [
    {"path": "/", "component": "DashboardPage", "label": "Dashboard"},
    {"path": "/projects", "component": "ProjectListPage", "label": "Projects"},
    {"path": "/projects/:id", "component": "ProjectDetailPage", "label": "Project"},
    {"path": "/projects/:id/editor", "component": "StoryEditorPage", "label": "Story Editor"},
    {"path": "/projects/:id/storyboard", "component": "StoryboardPage", "label": "Storyboard"},
    {"path": "/projects/:id/gallery", "component": "GalleryPage", "label": "Gallery"},
    {"path": "/projects/:id/timeline", "component": "TimelineEditorPage", "label": "Timeline"},
    {"path": "/projects/:id/export", "component": "ExportPage", "label": "Export"},
    {"path": "/jobs", "component": "JobMonitorPage", "label": "Jobs"},
    {"path": "/providers", "component": "ProviderSettingsPage", "label": "Providers"},
    {"path": "/settings", "component": "SettingsPage", "label": "Settings"},
]

COMPONENT_TREE = {
    "Layout": {
        "AppLayout": "Main layout with Sidebar + Header + Content",
        "Sidebar": "Navigation sidebar (project list, settings)",
        "Header": "Top bar (project name, user menu)",
        "Content": "Router outlet for page components",
    },
    "Dashboard": {
        "DashboardPage": "Overview page with stats and quick actions",
        "ProjectCard": "Project summary card",
        "RecentJobList": "Recent jobs status list",
    },
    "ProjectManagement": {
        "ProjectListPage": "List all projects with search/filter",
        "ProjectCreateModal": "Create new project dialog",
        "ProjectDeleteConfirm": "Delete confirmation dialog",
    },
    "StoryEditor": {
        "StoryEditorPage": "Rich text editor for manga script",
        "NovelInputPanel": "Paste/type novel text",
        "ChapterList": "Chapter sidebar with drag-drop reorder",
        "StoryParseResult": "Parsed story structure view",
    },
    "Storyboard": {
        "StoryboardPage": "Visual storyboard editor",
        "ShotCard": "Individual shot card with thumbnail",
        "ShotEditor": "Shot detail editor (prompt, camera, dialogue)",
        "ImagePreview": "Generated image preview with zoom",
        "CharacterPanel": "Character assignment panel",
    },
    "Timeline": {
        "TimelineEditorPage": "Multi-track timeline editor",
        "TrackList": "Track list with add/remove/lock",
        "ClipBlock": "Draggable clip block on timeline",
        "TimelineRuler": "Time ruler with frame markers",
        "PlaybackControls": "Play/pause/seek controls",
    },
    "Export": {
        "ExportPage": "Export settings and preview",
        "FormatSelector": "Export format picker (MP4/PDF/WEB)",
        "ResolutionSelector": "Resolution preset selector",
        "ExportProgressBar": "Export progress with ETA",
        "ExportResultView": "Export result with download link",
    },
    "JobMonitor": {
        "JobMonitorPage": "Real-time job monitoring",
        "JobCard": "Job status card with progress bar",
        "JobLogViewer": "Job log viewer with SSE",
        "JobCancelButton": "Cancel job button",
    },
    "ProviderSettings": {
        "ProviderSettingsPage": "AI provider configuration",
        "ProviderCard": "Provider card with health status",
        "ProviderConfigForm": "API key / endpoint configuration form",
        "ProviderTestButton": "Test connection button",
    },
}

STORE_SLICES = {
    "projectStore": {
        "state": ["projects", "currentProject", "loading"],
        "actions": ["fetchProjects", "createProject", "deleteProject", "selectProject"],
    },
    "storyboardStore": {
        "state": ["storyboards", "shots", "currentShot"],
        "actions": ["fetchStoryboards", "addShot", "updateShot", "deleteShot"],
    },
    "characterStore": {
        "state": ["characters", "loading"],
        "actions": ["fetchCharacters", "createCharacter", "updateCharacter"],
    },
    "jobStore": {
        "state": ["jobs", "activeJobs", "recentJobs"],
        "actions": ["submitJob", "cancelJob", "pollJobStatus"],
    },
    "assetStore": {
        "state": ["assets", "selectedAssets", "filterBy"],
        "actions": ["fetchAssets", "uploadAsset", "deleteAsset"],
    },
    "providerStore": {
        "state": ["providers", "healthStatus"],
        "actions": ["fetchProviders", "updateProviderConfig", "testProvider"],
    },
    "timelineStore": {
        "state": ["tracks", "clips", "playheadPosition", "isPlaying"],
        "actions": ["addTrack", "addClip", "moveClip", "removeClip", "setPlayhead"],
    },
}

API_CLIENT_STRUCTURE = {
    "apiClient.ts": "Axios instance with interceptors (JWT, error handling)",
    "projectsApi.ts": "Project CRUD endpoints",
    "charactersApi.ts": "Character CRUD endpoints",
    "storyboardsApi.ts": "Storyboard + Shot endpoints",
    "assetsApi.ts": "Asset management endpoints",
    "jobsApi.ts": "Job submission + monitoring (REST + SSE + WS)",
    "providersApi.ts": "Provider health + config endpoints",
    "exportApi.ts": "Export initiation + progress endpoints",
}
