from __future__ import annotations

import json
import math
import struct
import subprocess
from pathlib import Path

from backend.orchestration.database import OrchestrationDatabase
from backend.timeline.models import WaveformEnvelope


class WaveformService:
    def __init__(
        self,
        db: OrchestrationDatabase,
        *,
        projects_root: str | Path = "projects",
        ffmpeg_bin: str = "ffmpeg",
    ) -> None:
        self.db = db
        self.projects_root = Path(projects_root)
        self.ffmpeg_bin = ffmpeg_bin

    def get_or_build(self, project_id: str, artifact_id: int, *, bins: int = 512) -> WaveformEnvelope:
        if bins <= 0 or bins > 4096:
            raise ValueError("waveform bins must be between 1 and 4096")
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM artifacts WHERE id=? AND project_id=?",
                (artifact_id, project_id),
            ).fetchone()
        if row is None:
            raise ValueError("artifact does not belong to timeline project")

        source = Path(str(row["path"]))
        if not source.is_absolute():
            source = self.projects_root / project_id / source
        if not source.is_file():
            raise ValueError(f"waveform source missing: {source}")

        digest = str(row["sha256"])
        cache = self.projects_root / project_id / ".timeline_cache" / "waveforms" / f"{digest}-{bins}.json"
        if cache.is_file():
            payload = json.loads(cache.read_text(encoding="utf-8"))
            return WaveformEnvelope(
                artifact_id=artifact_id,
                bins=bins,
                peaks=[float(value) for value in payload.get("peaks", [])],
                cache_path=str(cache),
            )

        completed = subprocess.run(
            [
                self.ffmpeg_bin,
                "-v",
                "error",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "8000",
                "-f",
                "f32le",
                "pipe:1",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        sample_count = len(completed.stdout) // 4
        samples = struct.unpack(f"<{sample_count}f", completed.stdout[: sample_count * 4]) if sample_count else ()
        peaks = self._bucket_peaks(samples, bins)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps({"artifact_id": artifact_id, "sha256": digest, "bins": bins, "peaks": peaks}, separators=(",", ":")),
            encoding="utf-8",
        )
        return WaveformEnvelope(artifact_id=artifact_id, bins=bins, peaks=peaks, cache_path=str(cache))

    @staticmethod
    def _bucket_peaks(samples: tuple[float, ...], bins: int) -> list[float]:
        if not samples:
            return []
        bucket_count = min(bins, len(samples))
        bucket_size = math.ceil(len(samples) / bucket_count)
        raw = [
            max(abs(value) for value in samples[index : index + bucket_size])
            for index in range(0, len(samples), bucket_size)
        ]
        peak = max(raw) or 1.0
        return [min(1.0, max(0.0, value / peak)) for value in raw[:bins]]
