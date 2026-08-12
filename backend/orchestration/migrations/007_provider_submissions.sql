CREATE TABLE IF NOT EXISTS provider_submissions (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    provider TEXT NOT NULL,
    submission_key TEXT NOT NULL UNIQUE,
    remote_submission_id TEXT,
    status TEXT NOT NULL,
    submitted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_provider_submissions_job_step_attempt
ON provider_submissions(job_id, step_id, attempt);