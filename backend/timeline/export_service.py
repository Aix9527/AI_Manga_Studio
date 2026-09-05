from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel

from backend.orchestration.schemas import JobCreate
from backend.timeline.compiler import TimelineCompiler, TimelineOutputProfile
from backend.timeline.qc import TimelineQcService


class TimelineExportBlocked(ValueError):
    pass


class TimelineExportResult(BaseModel):
    snapshot_id: str
    composition_spec_id: str
    composition_spec_sha256: str
    job_id: str
    status: str
    artifact_id: int | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TimelineExportService:
    def __init__(self, timeline_repo, job_service):
        self.timeline_repo = timeline_repo
        self.job_service = job_service
        self.compiler = TimelineCompiler(timeline_repo)
        self.qc = TimelineQcService(timeline_repo)

    def export(self, snapshot_id: str, output_profile: TimelineOutputProfile) -> TimelineExportResult:
        qc_status = self.qc.get_status(snapshot_id)
        if qc_status.effective_status != "passed":
            raise TimelineExportBlocked(
                f"Snapshot QC must be passed before export; current state is {qc_status.effective_status}"
            )

        spec = self.compiler.compile(snapshot_id, output_profile)
        with self.timeline_repo.db.connect() as conn:
            binding = conn.execute(
                """SELECT * FROM timeline_export_bindings
                   WHERE composition_spec_id=? ORDER BY created_at DESC LIMIT 1""",
                (spec.id,),
            ).fetchone()
            snapshot = conn.execute(
                "SELECT state_json,state_sha256,snapshot_no FROM timeline_snapshots WHERE id=?",
                (snapshot_id,),
            ).fetchone()
        if snapshot is None:
            raise TimelineExportBlocked(f"Snapshot disappeared before export: {snapshot_id}")

        if binding is not None:
            job = self.job_service.repo.get_job(str(binding["job_id"]))
            if job is not None:
                return TimelineExportResult(
                    snapshot_id=snapshot_id,
                    composition_spec_id=spec.id,
                    composition_spec_sha256=spec.spec_sha256,
                    job_id=str(binding["job_id"]),
                    status=str(job["status"]),
                    artifact_id=int(binding["artifact_id"]) if binding["artifact_id"] is not None else None,
                )

        state = json.loads(str(snapshot["state_json"]))
        project_id = str(state.get("project_id", ""))
        if not project_id:
            raise TimelineExportBlocked("Snapshot project identity is missing")
        fps = output_profile.fps_num // output_profile.fps_den if output_profile.fps_num % output_profile.fps_den == 0 else round(output_profile.fps_num / output_profile.fps_den)
        provenance = {
            "source": "timeline_snapshot",
            "timeline_id": str(state.get("timeline_id", "")),
            "snapshot_id": snapshot_id,
            "snapshot_no": int(snapshot["snapshot_no"]),
            "state_sha256": str(snapshot["state_sha256"]),
            "composition_spec_id": spec.id,
            "composition_spec_sha256": spec.spec_sha256,
            "compiler_version": spec.compiler_version,
            "fps_num": output_profile.fps_num,
            "fps_den": output_profile.fps_den,
        }
        data = JobCreate(
            project_id=project_id,
            input_path="",
            input_type="timeline_snapshot",
            width=output_profile.width,
            height=output_profile.height,
            fps=fps,
            idempotency_key=f"timeline-export:{spec.spec_sha256}",
        )
        job = self.job_service.create_timeline_export(data, timeline=provenance)
        binding_id = f"timeline-export-{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        with self.timeline_repo.db.transaction(immediate=True) as conn:
            existing = conn.execute(
                """SELECT * FROM timeline_export_bindings
                   WHERE composition_spec_id=? ORDER BY created_at DESC LIMIT 1""",
                (spec.id,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """INSERT INTO timeline_export_bindings
                       (id,composition_spec_id,job_id,artifact_id,status,created_at,updated_at)
                       VALUES (?,?,?,NULL,?,?,?)""",
                    (binding_id, spec.id, job.id, job.status.value if hasattr(job.status, "value") else str(job.status), now, now),
                )
                existing = conn.execute(
                    "SELECT * FROM timeline_export_bindings WHERE id=?", (binding_id,)
                ).fetchone()
        return TimelineExportResult(
            snapshot_id=snapshot_id,
            composition_spec_id=spec.id,
            composition_spec_sha256=spec.spec_sha256,
            job_id=str(existing["job_id"]),
            status=str(job.status.value if hasattr(job.status, "value") else job.status),
            artifact_id=int(existing["artifact_id"]) if existing["artifact_id"] is not None else None,
        )
