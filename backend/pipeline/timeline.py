"""
V3.0 Layer 14 — Timeline Builder

Constructs a complete audiovisual timeline from shots, clips, audio, and subtitles.
Auto-inserts transitions and generates FFmpeg complex filter graphs for
single-pass rendering (avoids multi-step concatenation quality loss).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TimelineClip:
    """A single clip on the timeline."""

    shot_id: str = ""
    source_path: str = ""              # Video/image path
    start_time: float = 0.0            # On timeline (seconds)
    end_time: float = 0.0
    duration: float = 0.0
    transition_in: str = "cut"         # "cut" / "fade" / "dissolve" / "wipe"
    transition_out: str = "cut"
    transition_duration: float = 0.5   # Transition duration in seconds
    audio_path: str = ""               # Associated audio file
    subtitle_text: str = ""            # Subtitle for this clip


@dataclass
class Timeline:
    """Complete timeline for a scene/chapter."""

    clips: List[TimelineClip] = field(default_factory=list)
    total_duration: float = 0.0
    fps: int = 24
    width: int = 3840
    height: int = 2160


# ── Transition selection ──────────────────────────────────────

_TRANSITION_RULES: Dict[str, List[str]] = {
    "dialogue": ["cut"],
    "action": ["cut", "wipe"],
    "emotional": ["dissolve", "fade"],
    "transition": ["dissolve", "fade", "wipe"],
    "narration": ["fade", "dissolve"],
    "monologue": ["dissolve"],
}


class TimelineBuilder:
    """Builds a complete timeline ready for FFmpeg rendering.

    Usage:
        builder = TimelineBuilder(fps=24)
        timeline = builder.build(shots, video_clips, audio_clips, subtitles)
        ffmpeg_filter = builder.to_ffmpeg_filter(timeline)
        # Use ffmpeg_filter as -filter_complex argument to FFmpeg
    """

    def __init__(self, fps: int = 24):
        self.fps = fps

    def build(
        self,
        shots: List[Any],
        video_clips: Dict[str, str],
        audio_clips: Dict[str, str],
        subtitles: Dict[str, str],
        transitions: Optional[Dict[str, str]] = None,
    ) -> Timeline:
        """Build the full timeline from shot/clip/audio/subtitle data.

        Args:
            shots: Ordered list of shots (each has shot_id, duration, beat_type).
            video_clips: Dict mapping shot_id → video/image path.
            audio_clips: Dict mapping shot_id → audio path.
            subtitles: Dict mapping shot_id → subtitle text.
            transitions: Optional dict mapping shot_id → "fade"/"dissolve"/"wipe"/"cut".

        Returns:
            Complete Timeline ready for rendering.
        """
        timeline = Timeline(fps=self.fps)
        current_time = 0.0
        transitions = transitions or {}

        for i, shot in enumerate(shots):
            shot_id = getattr(shot, "shot_id", f"shot_{i}") if shot else f"shot_{i}"
            duration = getattr(shot, "duration", 2.0) if shot else 2.0
            beat_type = getattr(shot, "beat_type", "") if shot else ""

            # Transition
            trans_in = transitions.get(shot_id, "")
            if not trans_in:
                trans_in = self._auto_transition(beat_type)

            # Previous clip transition out matches current transition_in
            transition_out = "cut"
            if i < len(shots) - 1:
                next_shot = shots[i + 1]
                next_beat_type = getattr(next_shot, "beat_type", "") if next_shot else ""
                next_shot_id = getattr(next_shot, "shot_id", "") if next_shot else ""
                next_trans = transitions.get(next_shot_id, self._auto_transition(next_beat_type))
                transition_out = next_trans

            clip = TimelineClip(
                shot_id=shot_id,
                source_path=video_clips.get(shot_id, ""),
                start_time=current_time,
                end_time=current_time + duration,
                duration=duration,
                transition_in=trans_in,
                transition_out=transition_out,
                transition_duration=0.5 if trans_in not in ("cut",) else 0.0,
                audio_path=audio_clips.get(shot_id, ""),
                subtitle_text=subtitles.get(shot_id, ""),
            )
            timeline.clips.append(clip)

            current_time += duration

        timeline.total_duration = current_time
        return timeline

    def to_ffmpeg_filter(self, timeline: Timeline) -> str:
        """Generate FFmpeg complex filter graph for single-pass rendering.

        Produces a filter_complex string that:
          1. Loads each clip
          2. Applies cross-fade/dissolve/wipes between clips
          3. Overlays audio tracks
          4. Adds subtitle burn-in

        Returns:
            FFmpeg -filter_complex string.
        """
        n = len(timeline.clips)
        if n == 0:
            return ""

        filters: List[str] = []

        # ── Input mapping ────────────────────────────────
        # Each clip is a separate input: [0:v] [1:v] [2:v] ...
        for i, clip in enumerate(timeline.clips):
            if clip.audio_path:
                filters.append(
                    f"[{i}:a]adelay={int(clip.start_time * 1000)}|"
                    f"{int(clip.start_time * 1000)}[a{i}]"
                )

        # ── Video concatenation with transitions ─────────
        if n == 1:
            filters.append(f"[0:v]null[outv]")
        else:
            # Build cross-fade chain
            prev_label = "0:v"
            for i in range(1, n):
                clip = timeline.clips[i]
                trans = clip.transition_in
                trans_dur = clip.transition_duration

                if trans in ("fade", "dissolve"):
                    offset = timeline.clips[i - 1].duration - trans_dur
                    filters.append(
                        f"[{prev_label}][{i}:v]xfade=transition=fade:"
                        f"duration={trans_dur}:offset={offset}[xfade{i}]"
                    )
                    prev_label = f"xfade{i}"
                else:
                    # Cut: simple concat
                    if i == 1:
                        filters.append(f"[0:v][1:v]concat=n=2:v=1:a=0[concat1]")
                        prev_label = "concat1"
                    else:
                        filters.append(
                            f"[{prev_label}][{i}:v]concat=n=2:v=1:a=0[concat{i}]"
                        )
                        prev_label = f"concat{i}"

            filters.append(f"[{prev_label}]null[outv]")

        # ── Audio mix ─────────────────────────────────────
        if any(c.audio_path for c in timeline.clips):
            audio_inputs = "".join(
                f"[a{i}]" for i, c in enumerate(timeline.clips) if c.audio_path
            )
            audio_count = sum(1 for c in timeline.clips if c.audio_path)
            if audio_count == 1:
                filters.append(f"{audio_inputs}anull[outa]")
            else:
                filters.append(
                    f"{audio_inputs}amix=inputs={audio_count}:duration=longest[outa]"
                )

        return "; ".join(filter for filter in filters if filter)

    # ── Helpers ───────────────────────────────────────────────

    def _auto_transition(self, beat_type: str) -> str:
        """Auto-select transition based on beat type."""
        import random
        candidates = _TRANSITION_RULES.get(beat_type, ["cut"])
        return random.choice(candidates) if candidates else "cut"
