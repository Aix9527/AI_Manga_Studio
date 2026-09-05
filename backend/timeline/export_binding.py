from __future__ import annotations

import json
from datetime import datetime, timezone


class TimelineExportBindingError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def bind_latest_export_artifact(repo, job_id: str) -> int | None:
    """Bind a Timeline export job to the exact final video artifact it produced.

    Legacy/non-Timeline jobs are intentionally ignored. Timeline jobs fail
    closed when their frozen composition-spec binding is missing or when the
    final export artifact cannot be resolved.
    """
    with repo.db.transaction(immediate=True) as conn:
        job = conn.execute("SELECT settings FROM jobs WHERE id=?", (job_id,)).fetchone()
        if job is None:
            raise TimelineExportBindingError(f"Job not found: {job_id}")
        try:
            settings = json.loads(str(job["settings"] or "{}"))
        except json.JSONDecodeError as error:
            raise TimelineExportBindingError("Job settings are invalid JSON") from error
        timeline = settings.get("timeline") or {}
        if timeline.get("source") != "timeline_snapshot":
            return None

        composition_spec_id = str(timeline.get("composition_spec_id") or "")
        if not composition_spec_id:
            raise TimelineExportBindingError("Timeline composition_spec_id is missing")

        artifact = conn.execute(
            """SELECT id FROM artifacts
               WHERE job_id=? AND kind='video' AND active=1
               ORDER BY id DESC LIMIT 1""",
            (job_id,),
        ).fetchone()
        if artifact is None:
            raise TimelineExportBindingError("Timeline final export artifact is missing")
        artifact_id = int(artifact["id"])

        binding = conn.execute(
            """SELECT id FROM timeline_export_bindings
               WHERE job_id=? AND composition_spec_id=?
               ORDER BY updated_at DESC LIMIT 1""",
            (job_id, composition_spec_id),
        ).fetchone()
        if binding is None:
            raise TimelineExportBindingError(
                f"Timeline export binding missing for job {job_id} / spec {composition_spec_id}"
            )
        conn.execute(
            """UPDATE timeline_export_bindings
               SET artifact_id=?, status='completed', updated_at=?
               WHERE id=?""",
            (artifact_id, _now_iso(), str(binding["id"])),
        )
        return artifact_id
