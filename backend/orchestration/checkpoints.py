from __future__ import annotations

import json
import hashlib
from pathlib import Path

from backend.orchestration.database import OrchestrationDatabase


class CheckpointManager:
    def __init__(self, db: OrchestrationDatabase, checkpoint_dir: str):
        self.db = db
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def compute_input_hash(self, job_id: str, stage_input: dict) -> str:
        payload = json.dumps(stage_input, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def is_cached(self, job_id: str, stage_key: str, shot_id: str, input_hash: str) -> bool:
        cp = self.db.get_checkpoint(job_id, stage_key, shot_id)
        if cp and cp["input_hash"] == input_hash and cp["status"] == "completed":
            return True
        return False

    def save_artifacts(self, job_id: str, step_id: str, stage_key: str, input_hash: str) -> None:
        self.db.save_checkpoint(job_id, step_id, stage_key, "", input_hash)

    def artifacts_for_job(self, job_id: str) -> list[dict]:
        return self.db.get_artifacts(job_id)
