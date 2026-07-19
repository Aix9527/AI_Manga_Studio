ALTER TABLE jobs
ADD COLUMN create_request_json TEXT NOT NULL DEFAULT '{}';

-- V1-V3 did not retain a separate creation request. The mutable settings are
-- the only deterministic historical baseline available for those rows.
UPDATE jobs
SET create_request_json = settings_json;
