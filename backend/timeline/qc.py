from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from backend.timeline.media import MediaIdentityResolver, TimelineMediaIntegrityError, TimelineMediaNotFound
from backend.timeline.models import TimelineQcRunView, TimelineQcStatusView


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TimelineQcNotFound(ValueError):
    pass


class TimelineQcService:
    def __init__(self, repo):
        self.repo = repo
        self.resolver = MediaIdentityResolver(repo.db, projects_root=repo.projects_root)

    def run(self, snapshot_id: str) -> TimelineQcRunView:
        with self.repo.db.transaction(immediate=True) as conn:
            snapshot = conn.execute("SELECT * FROM timeline_snapshots WHERE id=?", (snapshot_id,)).fetchone()
            if snapshot is None:
                raise TimelineQcNotFound(f"Timeline snapshot not found: {snapshot_id}")
            attempt_row = conn.execute(
                "SELECT COALESCE(MAX(attempt),0)+1 AS attempt FROM timeline_snapshot_qc_runs WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
            attempt = int(attempt_row["attempt"])
            run_id = f"timeline-qc-{uuid.uuid4().hex[:12]}"
            started = _now_iso()
            conn.execute(
                """INSERT INTO timeline_snapshot_qc_runs
                   (id, snapshot_id, attempt, status, report_json, started_at, completed_at, created_at)
                   VALUES (?,?,?,'running','{}',?,NULL,?)""",
                (run_id, snapshot_id, attempt, started, started),
            )

        state = json.loads(str(snapshot["state_json"]))
        status, report = self._evaluate(state, int(snapshot["duration_tick"]))
        completed = _now_iso()
        encoded_report = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.repo.db.transaction(immediate=True) as conn:
            conn.execute(
                """UPDATE timeline_snapshot_qc_runs
                   SET status=?, report_json=?, completed_at=? WHERE id=?""",
                (status, encoded_report, completed, run_id),
            )
            row = conn.execute("SELECT * FROM timeline_snapshot_qc_runs WHERE id=?", (run_id,)).fetchone()
        return self._run_view(row)

    def get_status(self, snapshot_id: str) -> TimelineQcStatusView:
        with self.repo.db.connect() as conn:
            snapshot = conn.execute("SELECT id FROM timeline_snapshots WHERE id=?", (snapshot_id,)).fetchone()
            if snapshot is None:
                raise TimelineQcNotFound(f"Timeline snapshot not found: {snapshot_id}")
            rows = conn.execute(
                "SELECT * FROM timeline_snapshot_qc_runs WHERE snapshot_id=? ORDER BY attempt",
                (snapshot_id,),
            ).fetchall()
        attempts = [self._run_view(row) for row in rows]
        effective = attempts[-1].status if attempts else "not_run"
        return TimelineQcStatusView(snapshot_id=snapshot_id, effective_status=effective, attempts=attempts)

    def _evaluate(self, state: dict, duration_tick: int) -> tuple[str, dict[str, object]]:
        errors: list[dict[str, object]] = []
        if duration_tick <= 0:
            errors.append({"code": "SNAPSHOT_STRUCTURE_INVALID", "message": "Snapshot duration must be positive"})

        sources = state.get("source_artifacts", [])
        source_ids = {int(item["artifact_id"]) for item in sources if isinstance(item, dict) and "artifact_id" in item}
        for track in state.get("tracks", []):
            for clip in track.get("clips", []):
                if int(clip.get("duration_tick", 0)) <= 0 or int(clip.get("source_out_tick", 0)) <= int(clip.get("source_in_tick", 0)):
                    errors.append({"code": "SNAPSHOT_STRUCTURE_INVALID", "clip_id": clip.get("id", "")})
                artifact_id = clip.get("artifact_id")
                if artifact_id is not None and int(artifact_id) not in source_ids:
                    errors.append({"code": "SNAPSHOT_STRUCTURE_INVALID", "artifact_id": artifact_id})

        for source in sources:
            artifact_id = int(source["artifact_id"])
            try:
                identity = self.resolver.resolve_artifact(artifact_id, verify_sha=True)
            except (TimelineMediaIntegrityError, TimelineMediaNotFound) as error:
                return "stale", {"errors": [{"code": "SOURCE_INTEGRITY_FAILED", "artifact_id": artifact_id, "message": str(error)}]}
            if (
                identity.version != int(source.get("artifact_version", identity.version))
                or identity.path != str(source.get("path", identity.path))
                or identity.sha256 != str(source.get("sha256", identity.sha256))
            ):
                return "stale", {"errors": [{"code": "SOURCE_INTEGRITY_FAILED", "artifact_id": artifact_id, "message": "Frozen artifact identity no longer matches registry"}]}
            with self.repo.db.connect() as conn:
                artifact = conn.execute("SELECT quality_status FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
            quality = str(artifact["quality_status"] if artifact else "unreviewed").lower()
            if quality in {"failed", "fail"}:
                errors.append({"code": "SOURCE_QC_FAILED", "artifact_id": artifact_id})
            elif quality not in {"passed", "pass"}:
                errors.append({"code": "SOURCE_QC_PENDING", "artifact_id": artifact_id})

        if errors:
            return "failed", {"errors": errors}
        return "passed", {"errors": [], "checks": ["structure", "source_integrity", "source_qc"]}

    @staticmethod
    def _run_view(row) -> TimelineQcRunView:
        return TimelineQcRunView(
            id=str(row["id"]),
            snapshot_id=str(row["snapshot_id"]),
            attempt=int(row["attempt"]),
            status=str(row["status"]),
            report=json.loads(row["report_json"] or "{}"),
            started_at=str(row["started_at"]),
            completed_at=str(row["completed_at"]) if row["completed_at"] else None,
        )
