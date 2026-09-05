from __future__ import annotations

from pathlib import Path

from backend.video.composer import VideoComposer


def _spec(video_path: Path, audio_path: Path) -> dict:
    return {
        "schema_version": 1,
        "compiler_version": "timeline-compose/v1",
        "timebase": {"ticks_per_second": 1_000_000, "fps_num": 24, "fps_den": 1},
        "output": {"width": 1080, "height": 1920, "fps_num": 24, "fps_den": 1},
        "duration_tick": 2_000_000,
        "tracks": [
            {
                "id": "v1",
                "track_type": "video",
                "role": "video.main",
                "muted": False,
                "clips": [
                    {
                        "id": "clip-v1",
                        "source_path": str(video_path),
                        "timeline_start_tick": 0,
                        "duration_tick": 2_000_000,
                        "source_in_tick": 500_000,
                        "source_out_tick": 2_500_000,
                        "gain_db": None,
                        "enabled": True,
                    }
                ],
            },
            {
                "id": "a1",
                "track_type": "audio",
                "role": "audio.dialogue",
                "muted": False,
                "clips": [
                    {
                        "id": "clip-a1",
                        "source_path": str(audio_path),
                        "timeline_start_tick": 250_000,
                        "duration_tick": 1_000_000,
                        "source_in_tick": 0,
                        "source_out_tick": 1_000_000,
                        "gain_db": -3.0,
                        "enabled": True,
                    }
                ],
            },
        ],
        "transitions": [],
        "subtitle_cues": [
            {"id": "s1", "start_tick": 500_000, "end_tick": 1_500_000, "text": "Hello: timeline"}
        ],
    }


def test_compose_timeline_uses_pinned_trim_audio_timing_and_subtitle(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    audio = tmp_path / "dialogue.wav"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    output = tmp_path / "composition" / "composite.mp4"
    composer = VideoComposer(output_dir=tmp_path)
    captured: list[str] = []

    def fake_run(cmd, output_path):
        captured.extend(str(part) for part in cmd)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"composite")
        return output_path

    monkeypatch.setattr(composer, "_run_ffmpeg", fake_run)

    result = composer.compose_timeline(_spec(video, audio), output)

    command = " ".join(captured)
    assert result == output
    assert str(video) in command and str(audio) in command
    assert "trim=start=0.5:duration=2" in command
    assert "adelay=250|250" in command
    assert "volume=" in command
    assert "drawtext=" in command
    assert "Hello\\: timeline" in command
    assert "scale=1080:1920" in command


def test_compose_timeline_rejects_unapproved_transition_type(tmp_path):
    video = tmp_path / "video.mp4"
    audio = tmp_path / "dialogue.wav"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    spec = _spec(video, audio)
    spec["transitions"] = [
        {
            "from_clip_id": "clip-v1",
            "to_clip_id": "clip-v1",
            "transition_type": "arbitrary_ffmpeg_filter",
            "duration_tick": 250_000,
        }
    ]

    composer = VideoComposer(output_dir=tmp_path)

    try:
        composer.compose_timeline(spec, tmp_path / "out.mp4")
    except ValueError as error:
        assert "transition" in str(error).lower()
    else:
        raise AssertionError("unapproved transition type must fail closed")
