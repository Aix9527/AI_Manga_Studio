CREATE TABLE job_commands (
    idempotency_key TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_job_commands_job_id
    ON job_commands(job_id, created_at);
