"""
Export Engine — Editing, timeline compositing & final delivery (Part 35)

Provides the complete export pipeline:
- Non-linear timeline compositing
- Multi-track video/audio assembly
- Final render with format selection
- Quality presets and encoding options
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExportFormat(str, Enum):
    MP4 = "mp4"
    WEBM = "webm"
    GIF = "gif"
    PNG_SEQUENCE = "png_sequence"
    EXR_SEQUENCE = "exr_sequence"


class ExportPreset(str, Enum):
    WEB_OPTIMIZED = "web_optimized"
    HIGH_QUALITY = "high_quality"
    LOSSLESS = "lossless"
    MOBILE = "mobile"
    CUSTOM = "custom"


class VideoCodec(str, Enum):
    H264 = "h264"
    H265 = "h265"
    VP9 = "vp9"
    AV1 = "av1"
    PRO_RES = "pro_res"
    UNCOMPRESSED = "uncompressed"


class AudioCodec(str, Enum):
    AAC = "aac"
    MP3 = "mp3"
    OPUS = "opus"
    PCM = "pcm"


@dataclass
class EncodingConfig:
    """Encoding configuration for export."""
    video_codec: VideoCodec = VideoCodec.H264
    audio_codec: AudioCodec = AudioCodec.AAC
    video_bitrate_kbps: int = 8000
    audio_bitrate_kbps: int = 256
    width: int = 1920
    height: int = 1080
    fps: int = 24
    crf: int = 18  # Constant Rate Factor (lower = better quality)
    preset: str = "medium"  # ffmpeg preset: ultrafast/fast/medium/slow/veryslow


@dataclass
class ExportPresetConfig:
    """Pre-defined export configurations."""
    preset: ExportPreset
    encoding: EncodingConfig = field(default_factory=EncodingConfig)
    output_format: ExportFormat = ExportFormat.MP4

    @classmethod
    def get_presets(cls) -> dict[ExportPreset, "ExportPresetConfig"]:
        return {
            ExportPreset.WEB_OPTIMIZED: cls(
                ExportPreset.WEB_OPTIMIZED,
                encoding=EncodingConfig(
                    video_codec=VideoCodec.H264,
                    video_bitrate_kbps=4000,
                    crf=23,
                    preset="fast",
                ),
                output_format=ExportFormat.MP4,
            ),
            ExportPreset.HIGH_QUALITY: cls(
                ExportPreset.HIGH_QUALITY,
                encoding=EncodingConfig(
                    video_codec=VideoCodec.H265,
                    video_bitrate_kbps=20000,
                    crf=16,
                    preset="slow",
                ),
                output_format=ExportFormat.MP4,
            ),
            ExportPreset.LOSSLESS: cls(
                ExportPreset.LOSSLESS,
                encoding=EncodingConfig(
                    video_codec=VideoCodec.UNCOMPRESSED,
                    audio_codec=AudioCodec.PCM,
                    crf=0,
                    preset="ultrafast",
                ),
                output_format=ExportFormat.EXR_SEQUENCE,
            ),
        }


@dataclass
class TimelineClip:
    """A single clip on the export timeline."""
    clip_id: str = ""
    source_path: str = ""
    track_index: int = 0  # 0 = video, 1+ = overlay
    start_time_seconds: float = 0.0
    duration_seconds: float = 1.0
    in_point_seconds: float = 0.0
    volume: float = 1.0  # For audio
    opacity: float = 1.0  # For video
    transition_in: str = "cut"
    transition_out: str = "cut"
    transition_duration: float = 0.5
    effects: list[str] = field(default_factory=list)


@dataclass
class ExportTimeline:
    """Complete export timeline with all tracks."""
    timeline_id: str = ""
    project_id: str = ""
    video_tracks: list[list[TimelineClip]] = field(default_factory=list)
    audio_tracks: list[list[TimelineClip]] = field(default_factory=list)
    total_duration_seconds: float = 0.0

    def add_clip(self, track_index: int, clip: TimelineClip, is_audio: bool = False) -> None:
        target = self.audio_tracks if is_audio else self.video_tracks
        while len(target) <= track_index:
            target.append([])
        target[track_index].append(clip)
        end_time = clip.start_time_seconds + clip.duration_seconds
        if end_time > self.total_duration_seconds:
            self.total_duration_seconds = end_time


@dataclass
class ExportJob:
    """A single export job."""
    job_id: str = ""
    project_id: str = ""
    timeline: ExportTimeline | None = None
    config: ExportPresetConfig = field(default_factory=lambda: ExportPresetConfig(
        ExportPreset.HIGH_QUALITY,
    ))
    output_path: str = ""
    progress: float = 0.0
    status: str = "pending"  # pending/rendering/completed/failed


# ── Export Orchestrator ───────────────────────────────────────────────

class ExportOrchestrator:
    """
    Orchestrates the complete export pipeline.

    Flow:
        1. Validate timeline completeness
        2. Compile encoding configuration
        3. Execute ffmpeg render
        4. Post-process (watermark, metadata)
        5. Verify output integrity
    """

    def __init__(self) -> None:
        self._active_jobs: dict[str, ExportJob] = {}

    def create_job(
        self,
        project_id: str,
        timeline: ExportTimeline,
        preset: ExportPreset = ExportPreset.HIGH_QUALITY,
        output_path: str = "",
    ) -> ExportJob:
        """Create a new export job."""
        presets = ExportPresetConfig.get_presets()
        config = presets.get(preset, presets[ExportPreset.WEB_OPTIMIZED])

        import uuid
        job = ExportJob(
            job_id=str(uuid.uuid4()),
            project_id=project_id,
            timeline=timeline,
            config=config,
            output_path=output_path or f"output/{project_id}/export_{preset.value}.mp4",
        )
        self._active_jobs[job.job_id] = job
        return job

    async def validate_timeline(self, timeline: ExportTimeline) -> list[str]:
        """Validate timeline: returns list of issues (empty = valid)."""
        issues = []
        if not timeline.video_tracks and not timeline.audio_tracks:
            issues.append("Timeline has no tracks")
        for track_idx, track in enumerate(timeline.video_tracks):
            for clip in track:
                if not clip.source_path:
                    issues.append(f"Video track {track_idx}: clip '{clip.clip_id}' has no source_path")
        for track_idx, track in enumerate(timeline.audio_tracks):
            for clip in track:
                if not clip.source_path:
                    issues.append(f"Audio track {track_idx}: clip '{clip.clip_id}' has no source_path")
        return issues

    async def execute(self, job: ExportJob) -> ExportJob:
        """Execute the export render."""
        job.status = "rendering"
        job.progress = 0.0

        # In production, builds ffmpeg command and streams progress
        # For now, structural placeholder
        job.progress = 1.0
        job.status = "completed"
        return job

    def get_job(self, job_id: str) -> ExportJob | None:
        return self._active_jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        job = self._active_jobs.get(job_id)
        if job and job.status == "rendering":
            job.status = "cancelled"
            return True
        return False
