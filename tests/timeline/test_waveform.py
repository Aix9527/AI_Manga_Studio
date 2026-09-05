import hashlib
import json
import math
import struct
import wave
from pathlib import Path

from backend.orchestration.database import OrchestrationDatabase
from backend.timeline.waveform import WaveformService


def _write_wav(path: Path, *, seconds: float = 0.25, sample_rate: int = 8000) -> None:
    frames = bytearray()
    for index in range(int(seconds * sample_rate)):
        value = int(math.sin(index / 12.0) * 16000)
        frames.extend(struct.pack("<h", value))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(frames))


def _seed_audio(db: OrchestrationDatabase, project_root: Path, *, artifact_id: int, filename: str) -> tuple[Path, str]:
    project_id = "project-a"
    media_path = project_root / project_id / filename
    media_path.parent.mkdir(parents=True, exist_ok=True)
    _write_wav(media_path)
    digest = hashlib.sha256(media_path.read_bytes()).hexdigest()
    with db.transaction() as conn:
        conn.execute(
            """INSERT INTO jobs
               (id, project_id, status, input_path, input_type, settings, idempotency_key)
               VALUES (?,?, 'completed', '', 'novel', '{}', ?)""",
            (f"job-{artifact_id}", project_id, f"seed-{artifact_id}"),
        )
        conn.execute(
            """INSERT INTO job_steps
               (id, job_id, sequence, stage_key, shot_id, status)
               VALUES (?,?,0,'audio_tts','shot_001','completed')""",
            (f"step-{artifact_id}", f"job-{artifact_id}"),
        )
        conn.execute(
            """INSERT INTO artifacts
               (id, job_id, step_id, kind, path, sha256, metadata, active,
                project_id, version, stage_key, scene_id, shot_id, quality_status)
               VALUES (?,?,?,?,?,?,?,1,?,1,'audio_tts','','shot_001','passed')""",
            (
                artifact_id,
                f"job-{artifact_id}",
                f"step-{artifact_id}",
                "audio",
                filename,
                digest,
                json.dumps({"duration_tick": 250_000}),
                project_id,
            ),
        )
    return media_path, digest


def test_waveform_cache_is_sha_keyed_and_reused(tmp_path):
    projects_root = tmp_path / "projects"
    db = OrchestrationDatabase(str(tmp_path / "timeline.db"))
    _, digest = _seed_audio(db, projects_root, artifact_id=21, filename="voice.wav")
    service = WaveformService(db, projects_root=projects_root, ffmpeg_bin="ffmpeg")
    try:
        first = service.get_or_build("project-a", 21, bins=64)
        second = service.get_or_build("project-a", 21, bins=64)
    finally:
        db.close()

    expected = projects_root / "project-a" / ".timeline_cache" / "waveforms" / f"{digest}-64.json"
    assert first.cache_path == str(expected)
    assert second.cache_path == first.cache_path
    assert expected.is_file()
    assert second.peaks == first.peaks


def test_waveform_peaks_are_normalized_and_bounded_by_requested_bins(tmp_path):
    projects_root = tmp_path / "projects"
    db = OrchestrationDatabase(str(tmp_path / "timeline.db"))
    _seed_audio(db, projects_root, artifact_id=22, filename="voice.wav")
    service = WaveformService(db, projects_root=projects_root, ffmpeg_bin="ffmpeg")
    try:
        result = service.get_or_build("project-a", 22, bins=32)
    finally:
        db.close()

    assert 1 <= len(result.peaks) <= 32
    assert all(0.0 <= value <= 1.0 for value in result.peaks)


def test_different_source_sha_uses_a_different_cache_file(tmp_path):
    projects_root = tmp_path / "projects"
    db = OrchestrationDatabase(str(tmp_path / "timeline.db"))
    media_path, _ = _seed_audio(db, projects_root, artifact_id=23, filename="voice.wav")
    service = WaveformService(db, projects_root=projects_root, ffmpeg_bin="ffmpeg")
    try:
        first = service.get_or_build("project-a", 23, bins=16)
        _write_wav(media_path, seconds=0.3)
        new_digest = hashlib.sha256(media_path.read_bytes()).hexdigest()
        with db.transaction() as conn:
            conn.execute("UPDATE artifacts SET sha256=? WHERE id=23", (new_digest,))
        second = service.get_or_build("project-a", 23, bins=16)
    finally:
        db.close()

    assert second.cache_path != first.cache_path
    assert new_digest in second.cache_path
