from __future__ import annotations

import hashlib
import json


class TimelineRuntimeIntegrityError(ValueError):
    pass


def load_timeline_composition_spec(db, composition_spec_id: str, *, expected_sha256: str = "") -> dict:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM timeline_composition_specs WHERE id=?", (composition_spec_id,)
        ).fetchone()
    if row is None:
        raise TimelineRuntimeIntegrityError(f"Timeline composition spec not found: {composition_spec_id}")
    payload = str(row["spec_json"])
    actual = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    stored = str(row["spec_sha256"])
    if actual != stored:
        raise TimelineRuntimeIntegrityError("Timeline composition spec SHA does not match stored payload")
    if expected_sha256 and stored != expected_sha256:
        raise TimelineRuntimeIntegrityError("Timeline composition spec SHA does not match Job provenance")
    spec = json.loads(payload)
    if spec.get("schema_version") != 1 or spec.get("compiler_version") != "timeline-compose/v1":
        raise TimelineRuntimeIntegrityError("Unsupported Timeline composition spec version")
    return spec


def record_timeline_export_artifact(db, job_id: str, artifact_id: int) -> None:
    with db.transaction(immediate=True) as conn:
        binding = conn.execute(
            "SELECT id FROM timeline_export_bindings WHERE job_id=? ORDER BY created_at DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        if binding is None:
            return
        conn.execute(
            """UPDATE timeline_export_bindings
               SET artifact_id=?, status='completed', updated_at=datetime('now')
               WHERE id=?""",
            (artifact_id, binding["id"]),
        )
