CREATE UNIQUE INDEX IF NOT EXISTS idx_steps_job_id_id
    ON job_steps(job_id, id);

CREATE TABLE artifacts_v2 (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    metadata_json TEXT NOT NULL,
    validated_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(step_id, kind, path),
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY(job_id, step_id)
        REFERENCES job_steps(job_id, id) ON DELETE CASCADE
);

INSERT INTO artifacts_v2(
    id, job_id, step_id, kind, path, sha256, size,
    metadata_json, validated_at, active
)
SELECT
    id, job_id, step_id, kind, path, sha256, size,
    metadata_json, validated_at, active
FROM artifacts;

DROP TABLE artifacts;
ALTER TABLE artifacts_v2 RENAME TO artifacts;

CREATE TABLE review_actions_v2 (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    action TEXT NOT NULL,
    comment TEXT NOT NULL,
    patch_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY(job_id, step_id)
        REFERENCES job_steps(job_id, id) ON DELETE CASCADE
);

INSERT INTO review_actions_v2(
    id, job_id, step_id, action, comment, patch_json, created_at
)
SELECT id, job_id, step_id, action, comment, patch_json, created_at
FROM review_actions;

DROP TABLE review_actions;
ALTER TABLE review_actions_v2 RENAME TO review_actions;

DROP INDEX IF EXISTS idx_events_job_id;
CREATE INDEX idx_events_job_id
    ON job_events(job_id, id);
