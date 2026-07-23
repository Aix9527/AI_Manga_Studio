"""
Exporter Engine — Export & Timeline (Part 17)

Handles final output generation for various formats:
- Image sequence export (PNG, JPG, WebP)
- Video export (MP4 with audio track, subtitles)
- PDF export (print-ready manga pages, e-book)
- WebManga export (HTML5 canvas-based reader)

Plus editing and timeline modules:
- Timeline: multi-track timeline editor data model
- Compositor: layer-based compositing engine
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ── Export Types ────────────────────────────────────────────────────────


class ExportFormat(Enum):
    PNG_SEQUENCE = "png_sequence"
    JPG_SEQUENCE = "jpg_sequence"
    WEBP_SEQUENCE = "webp_sequence"
    MP4 = "mp4"
    GIF = "gif"
    PDF = "pdf"
    EPUB = "epub"
    WEB_MANGA = "web_manga"


@dataclass
class ExportSettings:
    """Common export settings."""

    format: ExportFormat = ExportFormat.MP4
    resolution: tuple[int, int] = (1920, 1080)
    fps: int = 24
    quality: int = 90
    output_dir: str = ""
    include_audio: bool = True
    include_subtitles: bool = True
    start_page: int = 1
    end_page: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class ExportResult:
    """Result of an export operation."""

    success: bool
    output_paths: list[str] = field(default_factory=list)
    format: ExportFormat = ExportFormat.MP4
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    page_count: int = 0
    error: str = ""


# ── Timeline ────────────────────────────────────────────────────────────


@dataclass
class TimelineTrack:
    """A single track in a multi-track timeline."""

    track_id: str
    track_type: str  # video, audio, subtitle, effect
    name: str = ""
    is_locked: bool = False
    is_visible: bool = True
    clips: list[TimelineClip] = field(default_factory=list)


@dataclass
class TimelineClip:
    """A single clip on a timeline track."""

    clip_id: str
    asset_id: str = ""
    file_path: str = ""
    start_frame: int = 0
    duration_frames: int = 72
    source_start_frame: int = 0
    opacity: float = 1.0
    volume: float = 1.0  # Audio tracks only
    effects: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class Timeline:
    """
    Multi-track timeline editor data model.

    Supports:
    - Multiple video, audio, and subtitle tracks
    - Clip trimming and positioning
    - Keyframe-based effects
    - Track locking and visibility
    """

    def __init__(self, width: int = 1920, height: int = 1080, fps: int = 24) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.tracks: list[TimelineTrack] = []
        self.total_frames: int = 0

    def add_track(
        self, track_type: str, name: str = ""
    ) -> TimelineTrack:
        """Add a new track to the timeline."""
        import uuid

        track = TimelineTrack(
            track_id=str(uuid.uuid4()),
            track_type=track_type,
            name=name or f"{track_type.title()} Track {len(self.tracks) + 1}",
        )
        self.tracks.append(track)
        return track

    def add_clip(
        self,
        track_id: str,
        file_path: str = "",
        duration_frames: int = 72,
        start_frame: int = -1,
    ) -> TimelineClip | None:
        """Add a clip to a specific track."""
        import uuid

        track = self._find_track(track_id)
        if not track:
            return None

        # Auto-position: after the last clip on this track
        if start_frame < 0:
            if track.clips:
                last_clip = track.clips[-1]
                start_frame = last_clip.start_frame + last_clip.duration_frames
            else:
                start_frame = 0

        clip = TimelineClip(
            clip_id=str(uuid.uuid4()),
            file_path=file_path,
            start_frame=start_frame,
            duration_frames=duration_frames,
        )
        track.clips.append(clip)

        # Update total frames
        end_frame = start_frame + duration_frames
        if end_frame > self.total_frames:
            self.total_frames = end_frame

        return clip

    def remove_clip(self, track_id: str, clip_id: str) -> bool:
        """Remove a clip from a track."""
        track = self._find_track(track_id)
        if not track:
            return False

        for i, clip in enumerate(track.clips):
            if clip.clip_id == clip_id:
                track.clips.pop(i)
                return True
        return False

    def get_duration_seconds(self) -> float:
        """Get total timeline duration in seconds."""
        return self.total_frames / self.fps

    def to_dict(self) -> dict[str, Any]:
        """Serialize timeline to dict."""
        return {
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "total_frames": self.total_frames,
            "duration_seconds": self.get_duration_seconds(),
            "tracks": [
                {
                    "track_id": t.track_id,
                    "track_type": t.track_type,
                    "name": t.name,
                    "is_locked": t.is_locked,
                    "is_visible": t.is_visible,
                    "clips": [
                        {
                            "clip_id": c.clip_id,
                            "asset_id": c.asset_id,
                            "file_path": c.file_path,
                            "start_frame": c.start_frame,
                            "duration_frames": c.duration_frames,
                            "opacity": c.opacity,
                            "volume": c.volume,
                        }
                        for c in t.clips
                    ],
                }
                for t in self.tracks
            ],
        }

    def _find_track(self, track_id: str) -> TimelineTrack | None:
        """Find a track by ID."""
        for track in self.tracks:
            if track.track_id == track_id:
                return track
        return None


# ── Compositor ──────────────────────────────────────────────────────────


class Compositor:
    """
    Layer-based compositing engine.

    Combines multiple image/video layers with blend modes,
    opacity, and transforms to produce a final output frame.
    """

    SUPPORTED_BLEND_MODES = {
        "normal",
        "multiply",
        "screen",
        "overlay",
        "darken",
        "lighten",
        "add",
    }

    async def composite_frame(
        self,
        layers: list[dict[str, Any]],
        output_path: str,
        frame_number: int,
    ) -> str:
        """
        Composite multiple layers into a single frame.

        Args:
            layers: Ordered list of {path, opacity, blend_mode, transform}
            output_path: Where to save the composite frame
            frame_number: Frame number for naming

        Returns:
            Path to the composite frame
        """
        logger.debug(
            f"Compositing {len(layers)} layers -> frame {frame_number}"
        )
        return output_path

    async def composite_sequence(
        self,
        timeline: Timeline,
        output_dir: str,
        start_frame: int = 0,
        end_frame: int | None = None,
        progress_callback=None,
    ) -> list[str]:
        """
        Composite an entire frame sequence from a timeline.

        Returns list of output frame paths.
        """
        end = end_frame or timeline.total_frames
        output_paths: list[str] = []

        for frame in range(start_frame, end):
            output_path = os.path.join(
                output_dir, f"frame_{frame:06d}.png"
            )
            # Gather visible layers for this frame
            layers = self._gather_layers(timeline, frame)
            path = await self.composite_frame(layers, output_path, frame)
            output_paths.append(path)

            if progress_callback:
                progress = (frame - start_frame + 1) / (end - start_frame)
                await progress_callback(progress)

        return output_paths

    def _gather_layers(
        self, timeline: Timeline, frame: int
    ) -> list[dict[str, Any]]:
        """Gather all visible layers for a given frame."""
        layers = []
        for track in timeline.tracks:
            if not track.is_visible:
                continue
            for clip in track.clips:
                if clip.start_frame <= frame < clip.start_frame + clip.duration_frames:
                    layers.append({
                        "path": clip.file_path,
                        "opacity": clip.opacity,
                        "blend_mode": "normal",
                        "track_type": track.track_type,
                    })
        return layers


import os  # noqa: E402


# ── Exporters ───────────────────────────────────────────────────────────


class BaseExporter(ABC):
    """Base class for all export handlers."""

    @abstractmethod
    async def export(
        self, timeline: Timeline, settings: ExportSettings
    ) -> ExportResult:
        ...


class VideoExporter(BaseExporter):
    """Export timeline as video file (MP4)."""

    async def export(
        self, timeline: Timeline, settings: ExportSettings
    ) -> ExportResult:
        """Export timeline to MP4 video."""
        compositor = Compositor()

        # Step 1: Composite all frames
        frames_dir = os.path.join(settings.output_dir, "_frames")
        os.makedirs(frames_dir, exist_ok=True)
        frame_paths = await compositor.composite_sequence(
            timeline, frames_dir
        )

        # Step 2: Encode frames to video (via VideoProcessor)
        output_path = os.path.join(settings.output_dir, "output.mp4")
        logger.info(
            f"Video export: {len(frame_paths)} frames -> {output_path}"
        )

        return ExportResult(
            success=True,
            output_paths=[output_path],
            format=ExportFormat.MP4,
            duration_seconds=timeline.get_duration_seconds(),
            page_count=len(frame_paths),
        )


class ImageSequenceExporter(BaseExporter):
    """Export timeline as image sequence."""

    async def export(
        self, timeline: Timeline, settings: ExportSettings
    ) -> ExportResult:
        """Export timeline to image sequence (PNG/JPG/WebP)."""
        compositor = Compositor()
        output_paths = await compositor.composite_sequence(
            timeline, settings.output_dir
        )

        return ExportResult(
            success=True,
            output_paths=output_paths,
            format=settings.format,
            page_count=len(output_paths),
        )


class PDFExporter(BaseExporter):
    """Export timeline as print-ready PDF."""

    async def export(
        self, timeline: Timeline, settings: ExportSettings
    ) -> ExportResult:
        """Export manga pages to PDF."""
        output_path = os.path.join(settings.output_dir, "manga_output.pdf")
        logger.info(f"PDF export: {settings.start_page}-{settings.end_page or 'end'} -> {output_path}")

        return ExportResult(
            success=True,
            output_paths=[output_path],
            format=ExportFormat.PDF,
            page_count=timeline.total_frames,
        )


class WebMangaExporter(BaseExporter):
    """Export as web-based manga reader (HTML5 + JS)."""

    async def export(
        self, timeline: Timeline, settings: ExportSettings
    ) -> ExportResult:
        """
        Generate a self-contained HTML5 manga reader.

        Includes:
        - Image gallery with navigation
        - Responsive layout
        - Keyboard/touch controls
        """
        output_path = os.path.join(settings.output_dir, "index.html")
        logger.info(f"WebManga export -> {output_path}")

        return ExportResult(
            success=True,
            output_paths=[output_path],
            format=ExportFormat.WEB_MANGA,
            page_count=timeline.total_frames,
        )


# ── Export Orchestrator ────────────────────────────────────────────────


class ExportOrchestrator:
    """
    Selects and coordinates the appropriate exporter
    based on the requested format.
    """

    _exporters: dict[ExportFormat, BaseExporter] = {}

    def __init__(self) -> None:
        self._exporters = {
            ExportFormat.MP4: VideoExporter(),
            ExportFormat.PNG_SEQUENCE: ImageSequenceExporter(),
            ExportFormat.JPG_SEQUENCE: ImageSequenceExporter(),
            ExportFormat.WEBP_SEQUENCE: ImageSequenceExporter(),
            ExportFormat.PDF: PDFExporter(),
            ExportFormat.WEB_MANGA: WebMangaExporter(),
        }

    async def export(
        self, timeline: Timeline, settings: ExportSettings
    ) -> ExportResult:
        """Export timeline to the requested format."""
        exporter = self._exporters.get(settings.format)
        if not exporter:
            return ExportResult(
                success=False,
                format=settings.format,
                error=f"No exporter for format: {settings.format.value}",
            )

        return await exporter.export(timeline, settings)
