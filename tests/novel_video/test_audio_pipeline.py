from __future__ import annotations

import math
import struct
import wave
from hashlib import sha256
from pathlib import Path

import pytest

from backend.novel_video.models import (
    AssetVersion,
    NovelVideoProject,
    ProductionMode,
    ProductionRun,
    ShotRecord,
)
from backend.novel_video.repository import NovelVideoRepository
from backend.orchestration.database import OrchestrationDatabase
from backend.production.contracts import (
    ChapterPlanBundle,
    DialogueLine,
    ScenePlan,
    ShotPlan,
)


def _write_wav(path: Path, *, duration: float = 0.4, tone: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 24_000
    samples = int(sample_rate * duration)
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frames = []
        for index in range(samples):
            value = 0
            if tone:
                value = int(0.35 * 32767 * math.sin(2 * math.pi * 440 * index / sample_rate))
            frames.append(value)
        handle.writeframes(struct.pack(f"<{len(frames)}h", *frames))
    return path


class FakeVoiceProvider:
    def __init__(self, tmp_path: Path, *, silent: bool = False) -> None:
        self.tmp_path = tmp_path
        self.silent = silent

    async def synthesize(self, text, profile, output: Path) -> Path:
        return _write_wav(output, tone=not self.silent)


@pytest.fixture
def audio_domain(tmp_path: Path):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel.db")))
    project = NovelVideoProject(id="project-audio", name="Audio", root=tmp_path / "project")
    repo.create_project(project)
    run = ProductionRun(
        id="run-audio",
        project_id=project.id,
        chapter_indexes=[1],
        mode=ProductionMode.ONE_CLICK,
        settings={"chapter_plan_id": "plan-audio"},
    )
    line = DialogueLine(speaker="机器人", text="我在沙漠里发现了一株绿色植物。", version_id="line-v1")
    shot = ShotPlan(
        id="shot-audio-1",
        sequence=1,
        scene_id="chapter-1",
        source_excerpt="银色机器人在夕阳沙漠中发现植物。",
        narrative_purpose="发现植物",
        duration_seconds=5,
        continuity="time_jump",
        inherit_tail=False,
        prompt="silver robot finds a green plant",
        negative_prompt="",
        dialogue=(line,),
        narration="夕阳把银色外壳染成金红。",
    )
    scene = ScenePlan(
        id="chapter-1",
        chapter_index=1,
        source_excerpt=shot.source_excerpt,
        narrative_purpose=shot.narrative_purpose,
        shots=(shot,),
    )
    bundle = ChapterPlanBundle(
        plan_version="v1",
        source_sha256="0" * 64,
        chapter_indexes=(1,),
        target_seconds=5,
        suggested_shot_count=1,
        scenes=(scene,),
        shots=(shot,),
        source_asset_version_id="source-audio",
        plan_id="plan-audio",
        max_shots=1,
    )
    repo.save_chapter_plan(project.id, bundle, source_asset_id="source-audio")
    repo.create_run_with_shots(
        run,
        [ShotRecord(id="shot-audio-1", run_id=run.id, chapter_id="chapter-1", sequence=1)],
    )
    return repo, project, run, scene, line


@pytest.mark.asyncio
async def test_dialogue_and_subtitle_share_text_version(audio_domain, tmp_path: Path):
    from backend.novel_video.audio import AudioPipeline

    repo, _project, run, chapter, line = audio_domain
    audio_pipeline = AudioPipeline(
        repo=repo,
        provider=FakeVoiceProvider(tmp_path),
        work_root=tmp_path / "audio-work",
    )

    bundle = await audio_pipeline.render_chapter(run.id, chapter.id)

    clip = next(c for c in bundle.dialogue if c.line_version_id == line.version_id)
    assert clip.text == line.text
    assert clip.path is not None
    assert clip.path.is_file()


@pytest.mark.asyncio
async def test_h3_audio_is_tagged_ambience_not_dialogue(audio_domain, tmp_path: Path):
    from backend.novel_video.audio import AudioPipeline

    repo, project, run, _chapter, _line = audio_domain
    video_path = tmp_path / "h3-with-audio.mp4"
    audio_path = tmp_path / "tone.wav"
    _write_wav(audio_path)
    import subprocess

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x64:d=0.4:r=24",
            "-i",
            str(audio_path),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(video_path),
        ],
        check=True,
    )
    h3_video = repo.append_asset(
        AssetVersion(
            id="h3-video-with-audio",
            project_id=project.id,
            run_id=run.id,
            shot_id="shot-audio-1",
            kind="video",
            state="approved",
            path=video_path,
            sha256=sha256(video_path.read_bytes()).hexdigest(),
        )
    )
    audio_pipeline = AudioPipeline(
        repo=repo,
        provider=FakeVoiceProvider(tmp_path),
        work_root=tmp_path / "audio-work",
    )

    clip = await audio_pipeline.extract_h3_ambience(h3_video)

    assert clip.kind == "ambience"
    assert clip.source_asset_id == h3_video.id
    assert clip.audio_present is True
    assert clip.line_version_id is None


@pytest.mark.asyncio
async def test_silent_tts_output_is_rejected(audio_domain, tmp_path: Path):
    from backend.novel_video.audio import AudioPipeline, AudioValidationError, VoiceProfile

    repo, _project, _run, _chapter, line = audio_domain
    audio_pipeline = AudioPipeline(
        repo=repo,
        provider=FakeVoiceProvider(tmp_path, silent=True),
        work_root=tmp_path / "audio-work",
    )

    with pytest.raises(AudioValidationError):
        await audio_pipeline.render_line(
            run_id="run-audio",
            shot_id="shot-audio-1",
            line=line,
            profile=VoiceProfile(),
        )


@pytest.mark.asyncio
async def test_no_text_narration_is_not_created(audio_domain, tmp_path: Path):
    from backend.novel_video.audio import AudioPipeline

    repo, _project, run, chapter, _line = audio_domain
    plan = repo.get_chapter_plan(run.project_id, (), plan_id=run.settings["chapter_plan_id"])
    shot = plan.shots[0]
    empty_shot = ShotPlan(
        **{
            **shot.__dict__,
            "dialogue": (),
            "narration": "   ",
        }
    )
    empty_plan = ChapterPlanBundle(
        **{
            **plan.__dict__,
            "plan_id": "plan-empty-narration",
            "target_seconds": 6,
            "shots": (empty_shot,),
            "scenes": (
                ScenePlan(
                    id=chapter.id,
                    chapter_index=1,
                    source_excerpt=empty_shot.source_excerpt,
                    narrative_purpose=empty_shot.narrative_purpose,
                    shots=(empty_shot,),
                ),
            ),
        }
    )
    repo.save_chapter_plan(run.project_id, empty_plan, source_asset_id="source-audio")
    repo.save_run(run.model_copy(update={"settings": {"chapter_plan_id": empty_plan.plan_id}}))
    audio_pipeline = AudioPipeline(
        repo=repo,
        provider=FakeVoiceProvider(tmp_path),
        work_root=tmp_path / "audio-work",
    )

    bundle = await audio_pipeline.render_chapter(run.id, chapter.id)

    assert bundle.narration == ()


@pytest.mark.asyncio
async def test_missing_h3_audio_is_explicit_without_synthetic_silence(audio_domain, tmp_path: Path):
    from backend.novel_video.audio import AudioPipeline

    repo, project, run, _chapter, _line = audio_domain
    video_path = tmp_path / "h3-no-audio.mp4"
    import subprocess

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x64:d=0.4:r=24",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video_path),
        ],
        check=True,
    )
    h3_video = repo.append_asset(
        AssetVersion(
            id="h3-video-no-audio",
            project_id=project.id,
            run_id=run.id,
            shot_id="shot-audio-1",
            kind="video",
            state="approved",
            path=video_path,
            sha256=sha256(video_path.read_bytes()).hexdigest(),
        )
    )
    audio_pipeline = AudioPipeline(
        repo=repo,
        provider=FakeVoiceProvider(tmp_path),
        work_root=tmp_path / "audio-work",
    )

    clip = await audio_pipeline.extract_h3_ambience(h3_video)

    assert clip.kind == "ambience"
    assert clip.source_asset_id == h3_video.id
    assert clip.audio_present is False
    assert clip.path is None
