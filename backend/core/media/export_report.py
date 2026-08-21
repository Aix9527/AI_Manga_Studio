from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any


@dataclass
class ExportReport:
    export_id: str
    project_id: str
    package_status: str

    resolution: str
    aspect_ratio: str
    fps: int

    video_sha256: str
    timeline_hash: str

    tracks: int
    clips: int

    subtitle_count: int
    audio_tracks: list[str]

    loudness_lufs: float | None
    true_peak_dbtp: float | None

    qc_result: str
    qc_score: float | None

    crop_mode: str | None
    template: str | None

    created_at: str


class ExportReportBuilder:
    """
    ExportPackage 最终生产报告生成器

    数据来源：
    - Timeline
    - FFmpeg Export Evidence
    - QualityEvaluation
    - LoudnessAnalyzer
    - SafeCropPlanner
    """


    def build(
        self,
        *,
        export_id: str,
        project_id: str,
        output_sha256: str,
        timeline_hash: str,
        resolution: str,
        aspect_ratio: str,
        fps: int,
        tracks: list[dict[str, Any]],
        subtitles: list[dict[str, Any]],
        audio_tracks: list[str],
        loudness: dict[str, float] | None,
        quality: dict[str, Any] | None,
        crop_mode: str | None = None,
        template: str | None = None,
    ) -> dict:


        clip_count = sum(
            len(track.get("clips", []))
            for track in tracks
        )


        report = ExportReport(

            export_id=export_id,

            project_id=project_id,

            package_status="completed",

            resolution=resolution,

            aspect_ratio=aspect_ratio,

            fps=fps,

            video_sha256=output_sha256,

            timeline_hash=timeline_hash,

            tracks=len(tracks),

            clips=clip_count,

            subtitle_count=len(subtitles),

            audio_tracks=audio_tracks,

            loudness_lufs=(
                loudness.get("lufs")
                if loudness
                else None
            ),

            true_peak_dbtp=(
                loudness.get("true_peak")
                if loudness
                else None
            ),

            qc_result=(
                quality.get("result")
                if quality
                else "UNKNOWN"
            ),

            qc_score=(
                quality.get("score")
                if quality
                else None
            ),

            crop_mode=crop_mode,

            template=template,

            created_at=datetime.utcnow()
            .isoformat()

        )


        return asdict(report)
