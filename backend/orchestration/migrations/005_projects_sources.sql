CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'archived')),
    mode TEXT NOT NULL DEFAULT 'automatic'
        CHECK(mode IN ('automatic', 'manual_review')),
    content_style TEXT NOT NULL DEFAULT 'live_action',
    target_duration_seconds INTEGER NOT NULL DEFAULT 60
        CHECK(target_duration_seconds BETWEEN 30 AND 90),
    width INTEGER NOT NULL DEFAULT 1080,
    height INTEGER NOT NULL DEFAULT 1920,
    fps INTEGER NOT NULL DEFAULT 24,
    quality_preset TEXT NOT NULL DEFAULT 'preview_then_quality',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE source_items (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK(kind IN ('idea', 'document', 'video', 'url')),
    original_name TEXT NOT NULL,
    original_location TEXT NOT NULL,
    managed_path TEXT NOT NULL DEFAULT '',
    sha256 TEXT NOT NULL DEFAULT '',
    rights_confirmed INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX idx_projects_status_updated
    ON projects(status, updated_at DESC);
CREATE INDEX idx_source_items_project_created
    ON source_items(project_id, created_at);
