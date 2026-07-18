CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    input_path TEXT NOT NULL,
    input_type TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    desired_state TEXT NOT NULL DEFAULT 'running',
    current_stage TEXT NOT NULL DEFAULT '',
    current_shot TEXT NOT NULL DEFAULT '',
    progress REAL NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    final_video TEXT NOT NULL DEFAULT '',
    settings_json TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    worker_id TEXT,
    lease_until TEXT,
    run_after TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS job_steps (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    stage_key TEXT NOT NULL,
    shot_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0,
    progress REAL NOT NULL DEFAULT 0,
    input_hash TEXT NOT NULL DEFAULT '',
    error_code TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    started_at TEXT,
    finished_at TEXT,
    UNIQUE(job_id, sequence, shot_id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    step_id TEXT NOT NULL REFERENCES job_steps(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    metadata_json TEXT NOT NULL,
    validated_at TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(step_id, kind, path)
);

CREATE TABLE IF NOT EXISTS job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_actions (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    step_id TEXT NOT NULL REFERENCES job_steps(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    comment TEXT NOT NULL,
    patch_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_created
    ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_steps_job_sequence
    ON job_steps(job_id, sequence);
CREATE INDEX IF NOT EXISTS idx_events_job_id
    ON job_events(job_id);
