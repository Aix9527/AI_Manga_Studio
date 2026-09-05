from pathlib import Path

path = Path("backend/orchestration/worker.py")
text = path.read_text(encoding="utf-8")
old = '                    self._register_artifact_simple(job_id, "video", str(final_path))\n'
new = (
    '                    self._register_artifact_simple(job_id, "video", str(final_path))\n'
    '                    from backend.timeline.export_binding import bind_latest_export_artifact\n'
    '                    bind_latest_export_artifact(self.repo, job_id)\n'
)
if new in text:
    raise SystemExit(0)
if text.count(old) != 1:
    raise SystemExit(f"export registration marker count={text.count(old)}")
path.write_text(text.replace(old, new), encoding="utf-8")
