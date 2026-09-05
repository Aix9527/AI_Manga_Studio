"""Video composer — combines images, audio, subtitles, and AI video clips into final MP4."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional


def _get_ffmpeg_binary() -> str:
    """Get the FFmpeg binary path, preferring a system FFmpeg when available.

    GPT P0: 优先系统 FFmpeg（新版支持 xfade 转场，且配套 ffprobe 可用于
    时长探测）；找不到时才回退 imageio-ffmpeg 的捆绑二进制（4.2.2 无 xfade）。
    """
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _get_ffprobe_binary() -> str:
    """Locate the ffprobe binary that ships alongside the selected ffmpeg.

    Never derive it via ``replace("ffmpeg", "ffprobe")``: for system installs
    like ``.../ffmpeg-master-latest-win64-gpl/bin/ffmpeg.EXE`` that produces
    a nonexistent path and every duration falls back to 5.0s, which breaks
    the xfade offsets in compose_episode (truncated 1-clip output).
    """
    ffmpeg = _FFMPEG_BIN
    cand = Path(ffmpeg).with_name("ffprobe" + Path(ffmpeg).suffix)
    if cand.is_file():
        return str(cand)
    cand_noext = Path(ffmpeg).with_name("ffprobe.exe")
    if cand_noext.is_file():
        return str(cand_noext)
    system_ffprobe = shutil.which("ffprobe")
    if system_ffprobe:
        return system_ffprobe
    return "ffprobe"


_FFMPEG_BIN = _get_ffmpeg_binary()


class VideoComposer:
    """Compose final video from generated assets using FFmpeg.

    Supports two modes:
    - Ken Burns: static image + zoom/pan + audio (legacy CLI-only; 已禁用，
      生产路径不再使用定帧兜底)
    - AI Video: Wan2.2-generated dynamic clips + audio (cinematic quality)
    """

    # Motion profiles for AI video generation (Wan2.2 motion_bucket_id)
    MOTION_PROFILES = {
        "static": 40,       # Minimal movement, talking head
        "subtle": 80,       # Slight camera movement
        "normal": 127,      # Balanced motion
        "dynamic": 180,     # Action/movement
        "intense": 240,     # Maximum motion
    }

    def __init__(self, output_dir: str | Path = "projects/output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def compose_shot(
        self,
        image_path: Path,
        audio_path: Optional[Path],
        output_path: Path,
        duration: float = 5.0,
        subtitle_text: str = "",
        fps: int = 24,
    ) -> Path:
        """Create a single shot video from image + audio (Ken Burns effect)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = self._build_shot_command(
            image_path, audio_path, output_path, duration, subtitle_text, fps
        )
        return self._run_ffmpeg(cmd, output_path)

    def compose_ai_shot(
        self,
        ai_video_path: Path,
        audio_path: Optional[Path],
        output_path: Path,
        subtitle_text: str = "",
        fontfile: Optional[str] = None,
    ) -> Path:
        """Compose a shot using an AI-generated video clip + audio + subtitles.

        Instead of Ken Burns on a static image, this uses the Wan2.2-generated
        dynamic video as the visual track, overlaying audio and subtitles.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not ai_video_path.exists():
            return output_path

        # Build FFmpeg command: AI video + audio + subtitles
        cmd = [_FFMPEG_BIN, "-y"]

        # Input: AI video
        cmd += ["-i", str(ai_video_path)]

        # Input: audio (optional)
        has_audio = audio_path and audio_path.exists()
        if has_audio:
            cmd += ["-i", str(audio_path)]

        # Video filter: scale to portrait + subtitles
        vf_parts = [
            "scale=1080:1920:force_original_aspect_ratio=decrease",
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        ]

        if subtitle_text:
            escaped_text = subtitle_text.replace("'", "'\\''").replace(":", "\\:")
            font_part = f"fontfile={fontfile.replace(':', '\\:')}:" if fontfile else ""
            vf_parts.append(
                f"drawtext={font_part}text='{escaped_text}':"
                f"fontcolor=white:fontsize=36:"
                f"x=(w-text_w)/2:y=h-120:"
                f"box=1:boxcolor=black@0.4:boxborderw=8"
            )

        vf_parts.append("format=yuv420p")
        cmd += ["-vf", ",".join(vf_parts)]

        if has_audio:
            cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "23"]
            cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
        else:
            cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-an"]

        cmd += [str(output_path)]
        return self._run_ffmpeg(cmd, output_path)

    def compose_sequence(
        self,
        shots: list[dict],
        output_path: Path,
        fps: int = 24,
        use_ai_video: bool = False,
    ) -> Path:
        """Compose multiple shots into a sequence.

        Args:
            shots: List of shot dicts with 'image', 'audio', 'duration', 'subtitle'
            output_path: Final output path
            fps: Frames per second
            use_ai_video: If True, require AI-generated video clips; a missing
                clip raises instead of falling back to a Ken Burns still frame.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        shot_videos = []
        concat_file = output_path.parent / "concat_list.txt"
        concat_lines = []

        for i, shot in enumerate(shots):
            shot_output = output_path.parent / f"shot_{i:03d}.mp4"

            if use_ai_video:
                # GPT P0: 只允许真实 AI 视频画面；缺 clip 直接报错，
                # 绝不退回到静态图（否则会产出"定帧假视频"）。
                ai_video_path = Path(shot.get("ai_video", ""))
                if not ai_video_path.exists():
                    raise FileNotFoundError(
                        f"AI video clip missing: {ai_video_path} "
                        f"(shot {i}, 已禁用 Ken Burns 定帧兜底)"
                    )
                audio_path = Path(shot["audio"]) if shot.get("audio") else None
                self.compose_ai_shot(
                    ai_video_path=ai_video_path,
                    audio_path=audio_path,
                    output_path=shot_output,
                    subtitle_text=shot.get("subtitle", ""),
                    fontfile=shot.get("fontfile"),
                )
            else:
                # Ken Burns mode
                self.compose_shot(
                    image_path=Path(shot["image"]),
                    audio_path=Path(shot["audio"]) if shot.get("audio") else None,
                    output_path=shot_output,
                    duration=shot.get("duration", 5.0),
                    subtitle_text=shot.get("subtitle", ""),
                    fps=fps,
                )

            concat_lines.append(f"file '{shot_output.name}'")
            shot_videos.append(shot_output)

        concat_file.write_text("\n".join(concat_lines), encoding="utf-8")

        cmd = [
            _FFMPEG_BIN, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        self._run_ffmpeg(cmd, output_path)

        for shot_video in shot_videos:
            if shot_video.exists():
                shot_video.unlink()
        if concat_file.exists():
            concat_file.unlink()

        return output_path

    def compose_timeline(self, spec: dict, output_path: Path) -> Path:
        """Render a canonical Timeline Composition Spec with the existing FFmpeg backend."""
        from decimal import Decimal, ROUND_HALF_UP
        import math

        if spec.get("schema_version") != 1 or spec.get("compiler_version") != "timeline-compose/v1":
            raise ValueError("Unsupported timeline composition spec")
        timebase = spec.get("timebase") or {}
        output = spec.get("output") or {}
        ticks_per_second = int(timebase.get("ticks_per_second") or 0)
        width = int(output.get("width") or 0)
        height = int(output.get("height") or 0)
        fps_num = int(output.get("fps_num") or 0)
        fps_den = int(output.get("fps_den") or 0)
        if ticks_per_second <= 0 or width <= 0 or height <= 0 or fps_num <= 0 or fps_den <= 0:
            raise ValueError("Invalid timeline timebase/output profile")

        allowed_transitions = {"cut", "crossfade", "fade_to_black", "fade_from_black"}
        transitions = spec.get("transitions") or []
        for transition in transitions:
            transition_type = str(transition.get("transition_type") or "cut")
            if transition_type not in allowed_transitions:
                raise ValueError(f"Unsupported timeline transition: {transition_type}")

        def seconds(tick: int) -> str:
            value = Decimal(int(tick)) / Decimal(ticks_per_second)
            rendered = format(value.normalize(), "f")
            return "0" if rendered == "-0" else rendered

        def millis(tick: int) -> int:
            value = (Decimal(int(tick)) * Decimal(1000) / Decimal(ticks_per_second)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
            return int(value)

        def escape_drawtext(value: str) -> str:
            return (
                value.replace("\\", "\\\\")
                .replace("'", "\\'")
                .replace(":", "\\:")
                .replace("%", "\\%")
                .replace("\n", "\\n")
            )

        tracks = spec.get("tracks") or []
        video_tracks = [t for t in tracks if t.get("role") == "video.main" and not t.get("muted")]
        if len(video_tracks) != 1:
            raise ValueError("v0.10 timeline renderer requires exactly one video.main track")
        video_clips = [c for c in video_tracks[0].get("clips", []) if c.get("enabled", True)]
        video_clips.sort(key=lambda c: (int(c.get("timeline_start_tick") or 0), str(c.get("id") or "")))
        if not video_clips:
            raise ValueError("Timeline composition has no enabled video clips")

        audio_clips: list[dict] = []
        for track in tracks:
            if track.get("track_type") == "audio" and not track.get("muted"):
                audio_clips.extend(c for c in track.get("clips", []) if c.get("enabled", True))
        audio_clips.sort(key=lambda c: (int(c.get("timeline_start_tick") or 0), str(c.get("id") or "")))

        input_args: list[str] = []
        for clip in video_clips:
            source = Path(str(clip.get("source_path") or ""))
            if not source.is_file():
                raise FileNotFoundError(f"Timeline video source missing: {source}")
            input_args.extend(["-i", str(source)])
        for clip in audio_clips:
            source = Path(str(clip.get("source_path") or ""))
            if not source.is_file():
                raise FileNotFoundError(f"Timeline audio source missing: {source}")
            input_args.extend(["-i", str(source)])

        filters: list[str] = []
        for index, clip in enumerate(video_clips):
            source_in = int(clip.get("source_in_tick") or 0)
            duration = int(clip.get("duration_tick") or 0)
            if duration <= 0:
                raise ValueError("Timeline video clip duration must be positive")
            filters.append(
                f"[{index}:v]trim=start={seconds(source_in)}:duration={seconds(duration)},"
                f"setpts=PTS-STARTPTS,scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps_num}/{fps_den},format=yuv420p[v{index}]"
            )

        transition_by_pair = {
            (str(t.get("from_clip_id") or ""), str(t.get("to_clip_id") or "")): t
            for t in transitions
        }
        current_video = "v0"
        accumulated_tick = int(video_clips[0].get("duration_tick") or 0)
        for index in range(1, len(video_clips)):
            previous, current = video_clips[index - 1], video_clips[index]
            transition = transition_by_pair.get((str(previous.get("id") or ""), str(current.get("id") or "")))
            transition_type = str((transition or {}).get("transition_type") or "cut")
            duration_tick = int((transition or {}).get("duration_tick") or 0)
            out = f"vchain{index}"
            if transition_type == "crossfade":
                if duration_tick <= 0:
                    raise ValueError("Crossfade transition duration must be positive")
                offset_tick = accumulated_tick - duration_tick
                if offset_tick < 0:
                    raise ValueError("Crossfade duration exceeds available timeline")
                filters.append(
                    f"[{current_video}][v{index}]xfade=transition=fade:duration={seconds(duration_tick)}:"
                    f"offset={seconds(offset_tick)}[{out}]"
                )
                accumulated_tick = offset_tick + int(current.get("duration_tick") or 0)
            else:
                left, right = current_video, f"v{index}"
                if transition_type == "fade_to_black" and duration_tick > 0:
                    faded = f"vfadeout{index}"
                    start_tick = max(0, accumulated_tick - duration_tick)
                    filters.append(
                        f"[{left}]fade=t=out:st={seconds(start_tick)}:d={seconds(duration_tick)}[{faded}]"
                    )
                    left = faded
                if transition_type == "fade_from_black" and duration_tick > 0:
                    faded = f"vfadein{index}"
                    filters.append(f"[{right}]fade=t=in:st=0:d={seconds(duration_tick)}[{faded}]")
                    right = faded
                filters.append(f"[{left}][{right}]concat=n=2:v=1:a=0[{out}]")
                accumulated_tick += int(current.get("duration_tick") or 0)
            current_video = out

        for index, cue in enumerate(spec.get("subtitle_cues") or []):
            text_value = str(cue.get("text") or "")
            start_tick = int(cue.get("start_tick") or 0)
            end_tick = int(cue.get("end_tick") or 0)
            if not text_value or end_tick <= start_tick:
                continue
            out = f"vsub{index}"
            filters.append(
                f"[{current_video}]drawtext=text='{escape_drawtext(text_value)}':"
                f"fontcolor=white:fontsize=36:x=(w-text_w)/2:y=h-120:"
                f"box=1:boxcolor=black@0.4:boxborderw=8:"
                f"enable='between(t,{seconds(start_tick)},{seconds(end_tick)})'[{out}]"
            )
            current_video = out

        current_audio: str | None = None
        audio_labels: list[str] = []
        audio_input_offset = len(video_clips)
        for index, clip in enumerate(audio_clips):
            source_in = int(clip.get("source_in_tick") or 0)
            duration = int(clip.get("duration_tick") or 0)
            start = int(clip.get("timeline_start_tick") or 0)
            if duration <= 0:
                raise ValueError("Timeline audio clip duration must be positive")
            gain_db = clip.get("gain_db")
            gain = math.pow(10.0, float(gain_db) / 20.0) if gain_db is not None else 1.0
            delay = max(0, millis(start))
            label = f"a{index}"
            filters.append(
                f"[{audio_input_offset + index}:a]atrim=start={seconds(source_in)}:duration={seconds(duration)},"
                f"asetpts=PTS-STARTPTS,adelay={delay}|{delay},volume={gain:.6f}[{label}]"
            )
            audio_labels.append(label)
        if len(audio_labels) == 1:
            current_audio = audio_labels[0]
        elif len(audio_labels) > 1:
            current_audio = "amixout"
            filters.append(
                "".join(f"[{label}]" for label in audio_labels)
                + f"amix=inputs={len(audio_labels)}:duration=longest:dropout_transition=0:normalize=0[{current_audio}]"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [_FFMPEG_BIN, "-y", *input_args, "-filter_complex", ";".join(filters), "-map", f"[{current_video}]"]
        if current_audio is not None:
            cmd.extend(["-map", f"[{current_audio}]", "-c:a", "aac", "-b:a", "192k"])
        else:
            cmd.append("-an")
        cmd.extend([
            "-c:v", "libx264", "-preset", "medium", "-crf", "21",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output_path),
        ])
        return self._run_ffmpeg(cmd, output_path)

    def compose_episode(
        self,
        video_paths: list[Path],
        output_path: Path,
        transition: str = "fade",
        transition_duration: float = 0.5,
        target_width: int = 1080,
        target_height: int = 1920,
        fps: int = 24,
    ) -> Path:
        """Compose multiple AI video clips into a single episode video.

        Normalises every clip to a uniform resolution, frame rate, and codec,
        then concatenates them.  When ``transition`` is ``"fade"``, a brief
        crossfade is applied at each shot boundary for smooth continuity —
        this is especially important for tail-frame-linked shots where the
        end of one clip should blend seamlessly into the start of the next.

        Args:
            video_paths: Ordered list of video file paths to concatenate.
            output_path: Destination path for the combined episode video.
            transition: Transition type — ``"fade"`` (crossfade) or
                ``"cut"`` (hard cut, fastest).
            transition_duration: Crossfade duration in seconds (0.2–2.0).
            target_width: Normalised output width (1080 for 9:16 portrait).
            target_height: Normalised output height (1920 for 9:16 portrait).
            fps: Target frame rate.

        Returns:
            Path to the composed episode video.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Filter to existing videos only
        valid_paths = [Path(p) for p in video_paths if Path(p).exists()]
        if not valid_paths:
            raise FileNotFoundError("No valid video files found for episode composition")

        # Single shot — just normalise and copy
        if len(valid_paths) == 1:
            cmd = [
                _FFMPEG_BIN, "-y",
                "-i", str(valid_paths[0]),
                "-vf", (
                    f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
                    f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,"
                    f"fps={fps},format=yuv420p"
                ),
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                str(output_path),
            ]
            return self._run_ffmpeg(cmd, output_path)

        if transition == "fade" and len(valid_paths) >= 2:
            return self._compose_with_crossfade(
                valid_paths, output_path,
                transition_duration, target_width, target_height, fps,
            )

        # Hard-cut concat: normalise each clip, then use concat demuxer
        return self._compose_with_concat(
            valid_paths, output_path,
            target_width, target_height, fps,
        )

    def _compose_with_concat(
        self,
        video_paths: list[Path],
        output_path: Path,
        target_width: int,
        target_height: int,
        fps: int,
    ) -> Path:
        """Concatenate clips using FFmpeg concat demuxer (fast, hard cuts).

        Each clip is first re-encoded to a uniform format, then the
        concat demuxer joins them without re-encoding the final output.
        """
        work_dir = output_path.parent / "_normalized"
        work_dir.mkdir(parents=True, exist_ok=True)

        normalized_paths: list[Path] = []
        concat_lines: list[str] = []

        for i, vp in enumerate(video_paths):
            norm_path = work_dir / f"norm_{i:03d}.mp4"
            cmd = [
                _FFMPEG_BIN, "-y",
                "-i", str(vp),
                "-vf", (
                    f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
                    f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,"
                    f"fps={fps},format=yuv420p"
                ),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-r", str(fps),
                str(norm_path),
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=120)
                if result.returncode == 0 and norm_path.exists():
                    normalized_paths.append(norm_path)
                    safe = str(norm_path).replace("'", "'\\''")
                    concat_lines.append(f"file '{safe}'")
                else:
                    # Fallback: try copy without re-encode
                    cmd_copy = [
                        _FFMPEG_BIN, "-y",
                        "-i", str(vp),
                        "-c", "copy",
                        str(norm_path),
                    ]
                    result2 = subprocess.run(cmd_copy, capture_output=True, encoding="utf-8", errors="replace", timeout=60)
                    if result2.returncode == 0 and norm_path.exists():
                        normalized_paths.append(norm_path)
                        safe = str(norm_path).replace("'", "'\\''")
                        concat_lines.append(f"file '{safe}'")
            except subprocess.TimeoutExpired:
                pass

        if not normalized_paths:
            raise RuntimeError("Failed to normalize any video clips for concat")

        concat_file = work_dir / "concat_list.txt"
        concat_file.write_text("\n".join(concat_lines), encoding="utf-8")

        # Concat
        cmd = [
            _FFMPEG_BIN, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ]
        self._run_ffmpeg(cmd, output_path)

        # Cleanup normalized intermediates
        for np in normalized_paths:
            try:
                np.unlink()
            except OSError:
                pass
        try:
            concat_file.unlink()
        except OSError:
            pass

        return output_path

    def _compose_with_crossfade(
        self,
        video_paths: list[Path],
        output_path: Path,
        transition_duration: float,
        target_width: int,
        target_height: int,
        fps: int,
    ) -> Path:
        """Concatenate clips with crossfade transitions using xfade filter.

        Uses FFmpeg's ``xfade`` filter to blend consecutive clips.  Each clip
        is first scaled/padded to uniform dimensions, then chained through
        xfade filters with configurable duration.

        For N clips, this produces a single seamless video where each
        boundary has a ``transition_duration``-second crossfade.
        """
        # Clamp transition duration
        td = max(0.2, min(2.0, transition_duration))

        # Step 1: Normalise all clips to uniform format
        work_dir = output_path.parent / "_xfade_norm"
        work_dir.mkdir(parents=True, exist_ok=True)

        norm_paths: list[Path] = []
        durations: list[float] = []

        for i, vp in enumerate(video_paths):
            norm_path = work_dir / f"clip_{i:03d}.mp4"
            cmd = [
                _FFMPEG_BIN, "-y",
                "-i", str(vp),
                "-vf", (
                    f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
                    f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,"
                    f"fps={fps},format=yuv420p"
                ),
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-b:a", "128k",
                "-r", str(fps),
                str(norm_path),
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=180)
                if result.returncode == 0 and norm_path.exists():
                    norm_paths.append(norm_path)
                    # Get duration via ffprobe
                    dur = self._get_video_duration(norm_path)
                    durations.append(dur)
                else:
                    # Fallback: copy as-is
                    cmd_copy = [_FFMPEG_BIN, "-y", "-i", str(vp), "-c", "copy", str(norm_path)]
                    subprocess.run(cmd_copy, capture_output=True, encoding="utf-8", errors="replace", timeout=60)
                    if norm_path.exists():
                        norm_paths.append(norm_path)
                        durations.append(self._get_video_duration(norm_path))
            except subprocess.TimeoutExpired:
                pass

        if len(norm_paths) < 2:
            # Not enough clips for crossfade; fall back to concat
            if norm_paths:
                return self._compose_with_concat(
                    norm_paths, output_path, target_width, target_height, fps,
                )
            raise RuntimeError("No clips available for crossfade composition")

        # Step 2: Build xfade filter chain
        # For N clips with crossfade of duration td:
        #   total_offset = sum of (duration[i] - td) for i < N-1
        #   [0:v][1:v]xfade=transition=fade:duration=td:offset=offset0[v01]
        #   [v01][2:v]xfade=transition=fade:duration=td:offset=offset1[v012]
        #   ...
        filter_parts: list[str] = []
        input_args: list[str] = []

        for np in norm_paths:
            input_args.extend(["-i", str(np)])

        prev_label = "0:v"
        offset = 0.0

        for i in range(1, len(norm_paths)):
            # Calculate offset: cumulative duration minus crossfade overlaps
            offset += durations[i - 1] - td
            if offset < 0:
                offset = 0.0

            out_label = f"v{i}" if i < len(norm_paths) - 1 else "vout"
            filter_parts.append(
                f"[{prev_label}][{i}:v]xfade=transition=fade:duration={td}:offset={offset:.3f}[{out_label}]"
            )
            prev_label = out_label

        # Also handle audio: acrossfade for smooth audio transitions
        audio_filter_parts: list[str] = []
        prev_a_label = "0:a"
        for i in range(1, len(norm_paths)):
            out_a = f"a{i}" if i < len(norm_paths) - 1 else "aout"
            audio_filter_parts.append(
                f"[{prev_a_label}][{i}:a]acrossfade=d={td}[{out_a}]"
            )
            prev_a_label = out_a

        filter_complex = ";".join(filter_parts + audio_filter_parts)

        cmd = [
            _FFMPEG_BIN, "-y",
            *input_args,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "21",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ]

        try:
            self._run_ffmpeg(cmd, output_path)
        except RuntimeError:
            # Fallback to concat if xfade fails
            return self._compose_with_concat(
                norm_paths, output_path, target_width, target_height, fps,
            )

        # Cleanup
        for np in norm_paths:
            try:
                np.unlink()
            except OSError:
                pass
        try:
            work_dir.rmdir()
        except OSError:
            pass

        return output_path

    @staticmethod
    def _get_video_duration(video_path: Path) -> float:
        """Get video duration in seconds using ffprobe."""
        ffprobe = _get_ffprobe_binary()
        try:
            result = subprocess.run(
                [ffprobe, "-v", "quiet",
                 "-show_entries", "format=duration",
                 "-of", "csv=p=0",
                 str(video_path)],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except (ValueError, FileNotFoundError, subprocess.TimeoutExpired):
            pass
        # Fallback: estimate from file size (rough)
        return 5.0

    def add_background_music(
        self,
        video_path: Path,
        music_path: Optional[Path],
        output_path: Path,
        music_volume: float = 0.3,
    ) -> Path:
        """Add background music to a video."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not music_path or not music_path.exists():
            if video_path != output_path:
                shutil.copy2(video_path, output_path)
            return output_path

        cmd = [
            _FFMPEG_BIN, "-y",
            "-i", str(video_path),
            "-i", str(music_path),
            "-filter_complex",
            f"[1:a]volume={music_volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            str(output_path),
        ]
        return self._run_ffmpeg(cmd, output_path)

    def export_final(
        self,
        video_path: Path,
        output_path: Path,
        format: str = "mp4",
        crf: int = 23,
        preset: str = "medium",
    ) -> Path:
        """Export final video with optimal settings."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if format == "mp4":
            cmd = [
                _FFMPEG_BIN, "-y",
                "-i", str(video_path),
                "-c:v", "libx264",
                "-preset", preset,
                "-crf", str(crf),
                "-c:a", "aac",
                "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(output_path),
            ]
        elif format == "webm":
            cmd = [
                _FFMPEG_BIN, "-y",
                "-i", str(video_path),
                "-c:v", "libvpx-vp9",
                "-crf", str(crf),
                "-b:v", "0",
                "-c:a", "libopus",
                str(output_path),
            ]
        else:
            raise ValueError(f"Unsupported export format: {format}")

        return self._run_ffmpeg(cmd, output_path)

    def _build_shot_command(
        self,
        image_path: Path,
        audio_path: Optional[Path],
        output_path: Path,
        duration: float,
        subtitle_text: str,
        fps: int,
    ) -> list[str]:
        """Build FFmpeg command for a single shot (Ken Burns mode)."""
        cmd = [_FFMPEG_BIN, "-y"]

        cmd += [
            "-loop", "1",
            "-i", str(image_path),
            "-t", str(duration),
            "-r", str(fps),
        ]

        has_audio = audio_path and audio_path.exists()
        if has_audio:
            cmd += ["-i", str(audio_path)]

        vf_parts = []
        vf_parts.append(
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
        )
        vf_parts.append(
            f"zoompan=z='min(zoom+0.0005,1.02)':d=1:x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':fps={fps}"
        )
        vf_parts.append("format=yuv420p")

        if subtitle_text:
            escaped_text = subtitle_text.replace("'", "'\\''").replace(":", "\\:")
            vf_parts.append(
                f"drawtext=text='{escaped_text}':"
                f"fontcolor=white:fontsize=36:"
                f"x=(w-text_w)/2:y=h-120:"
                f"box=1:boxcolor=black@0.4:boxborderw=8"
            )

        cmd += ["-vf", ",".join(vf_parts)]

        if has_audio:
            cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
        else:
            cmd += ["-an"]

        cmd += [str(output_path)]
        return cmd

    @staticmethod
    def _run_ffmpeg(cmd: list[str], output_path: Path) -> Path:
        """Run FFmpeg command with error handling.

        GPT P0: 失败即失败 —— 任何 FFmpeg 错误都直接抛出，绝不创建
        0 字节占位文件冒充成功输出（那是另一种"假视频"）。
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"FFmpeg binary not found: {cmd[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"FFmpeg timed out: {cmd[0]}") from exc
        if result.returncode != 0:
            err_tail = result.stderr[-500:] if result.stderr else ""
            raise RuntimeError(f"FFmpeg failed: {err_tail}")
        return output_path


def check_ffmpeg() -> bool:
    """Check if FFmpeg is available."""
    try:
        subprocess.run([_FFMPEG_BIN, "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False