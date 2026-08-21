from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal, Protocol

from backend.audio.tts_engine import TTSEngine
from backend.novel_video.models import AssetVersion
from backend.novel_video.repository import NovelVideoRepository
from backend.novel_video.storage import AtomicAssetStore


class AudioValidationError(ValueError):
    """Raised when generated audio cannot be admitted as a versioned asset."""


@dataclass(frozen=True)
class VoiceProfile:
    voice: str = TTSEngine.VOICE_CN_FEMALE
    emotion: str = "neutral"
    rate: str = "+0%"
    pitch: str = "+0Hz"
    reference_audio: Path | None = None


class VoiceProvider(Protocol):
    async def synthesize(self, text: str, profile: VoiceProfile, output: Path) -> Path:
        ...


@dataclass(frozen=True)
class AudioClip:
    id: str
    kind: Literal["dialogue", "narration", "ambience", "sfx", "music"]
    path: Path | None
    start_seconds: float
    duration_seconds: float
    source_asset_id: str | None
    line_version_id: str | None
    text: str
    audio_present: bool = True
    asset_id: str | None = None


@dataclass(frozen=True)
class AudioBundle:
    id: str
    run_id: str
    chapter_id: str
    dialogue: tuple[AudioClip, ...] = ()
    narration: tuple[AudioClip, ...] = ()
    ambience: tuple[AudioClip, ...] = ()


class AudioPipeline:
    def __init__(
        self,
        *,
        repo: NovelVideoRepository,
        provider: VoiceProvider | None = None,
        asset_store: AtomicAssetStore | None = None,
        work_root: Path | str | None = None,
        min_duration_seconds: float = 0.10,
        min_mean_volume_db: float = -55.0,
    ) -> None:
        self.repo = repo
        self.provider = provider or TTSEngine()
        self.asset_store = asset_store or AtomicAssetStore()
        self.work_root = Path(work_root) if work_root is not None else Path("projects/output/novel-video-audio")
        self.min_duration_seconds = min_duration_seconds
        self.min_mean_volume_db = min_mean_volume_db

    async def render_chapter(
        self,
        run_id: str,
        chapter_id: str,
        *,
        profile: VoiceProfile | None = None,
    ) -> AudioBundle:
        run = self.repo.get_run(run_id)
        if run is None:
            raise KeyError(f"run {run_id} does not exist")
        plan_id = str(run.settings.get("chapter_plan_id") or "")
        if not plan_id:
            raise ValueError("run does not reference an immutable chapter plan")
        plan = self.repo.get_chapter_plan(run.project_id, (), plan_id=plan_id)
        if plan is None:
            raise KeyError(f"chapter plan {plan_id} does not exist")

        dialogue: list[AudioClip] = []
        narration: list[AudioClip] = []
        selected = [
            shot for shot in plan.shots
            if chapter_id in {shot.scene_id, shot.id, str(getattr(shot, "chapter_id", ""))}
        ]
        if not selected:
            scene_ids = {scene.id for scene in plan.scenes if str(scene.chapter_index) == str(chapter_id)}
            selected = [shot for shot in plan.shots if shot.scene_id in scene_ids]
        for shot in selected:
            start_seconds = self._shot_start_seconds(plan.shots, shot.id)
            for index, line in enumerate(shot.dialogue):
                text = str(getattr(line, "text", ""))
                if not text.strip():
                    continue
                dialogue.append(
                    await self.render_line(
                        run_id=run_id,
                        shot_id=shot.id,
                        line=line,
                        profile=profile or VoiceProfile(),
                        start_seconds=start_seconds,
                        line_index=index,
                    )
                )
            if shot.narration.strip():
                narration.append(
                    await self.render_narration(
                        run_id=run_id,
                        shot_id=shot.id,
                        text=shot.narration,
                        profile=profile or VoiceProfile(voice=TTSEngine.VOICE_CN_NARRATOR),
                        start_seconds=start_seconds,
                    )
                )
        return AudioBundle(
            id=f"audio-bundle-{sha256(f'{run_id}:{chapter_id}:{plan_id}'.encode()).hexdigest()[:16]}",
            run_id=run_id,
            chapter_id=chapter_id,
            dialogue=tuple(dialogue),
            narration=tuple(narration),
        )

    async def render_line(
        self,
        *,
        run_id: str,
        shot_id: str,
        line,
        profile: VoiceProfile,
        start_seconds: float = 0.0,
        line_index: int = 0,
    ) -> AudioClip:
        text = str(getattr(line, "text", ""))
        if not text.strip():
            raise AudioValidationError("dialogue text is empty")
        line_version_id = self._line_version_id(line, shot_id, line_index, kind="dialogue")
        return await self._render_text_clip(
            run_id=run_id,
            shot_id=shot_id,
            kind="dialogue",
            text=text,
            line_version_id=line_version_id,
            profile=profile,
            start_seconds=start_seconds,
        )

    async def render_narration(
        self,
        *,
        run_id: str,
        shot_id: str,
        text: str,
        profile: VoiceProfile,
        start_seconds: float = 0.0,
    ) -> AudioClip:
        if not text.strip():
            raise AudioValidationError("narration text is empty")
        line_version_id = self._line_version_id(
            type("NarrationLine", (), {"speaker": "narrator", "text": text, "version_id": ""})(),
            shot_id,
            0,
            kind="narration",
        )
        return await self._render_text_clip(
            run_id=run_id,
            shot_id=shot_id,
            kind="narration",
            text=text,
            line_version_id=line_version_id,
            profile=profile,
            start_seconds=start_seconds,
        )

    async def extract_h3_ambience(self, h3_video: AssetVersion) -> AudioClip:
        if h3_video.kind != "video":
            raise ValueError("H3 ambience can only be extracted from a video asset")
        if not h3_video.path.is_file():
            raise FileNotFoundError(h3_video.path)
        if not self._has_audio_stream(h3_video.path):
            return AudioClip(
                id=f"ambience-missing-{h3_video.id}",
                kind="ambience",
                path=None,
                start_seconds=0.0,
                duration_seconds=0.0,
                source_asset_id=h3_video.id,
                line_version_id=None,
                text="",
                audio_present=False,
            )

        run = self.repo.get_run(h3_video.run_id)
        if run is None:
            raise KeyError(f"run {h3_video.run_id} does not exist")
        project = self.repo.get_project(h3_video.project_id)
        if project is None:
            raise KeyError(f"project {h3_video.project_id} does not exist")
        temp_path = self._temp_path(h3_video.run_id, h3_video.shot_id or "run", "ambience", ".wav")
        command = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-i",
            str(h3_video.path),
            "-map",
            "0:a:0?",
            "-vn",
            "-acodec",
            "pcm_s16le",
            str(temp_path),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        duration, mean_volume = self._validate_audio(temp_path)
        final_path = project.root / "audio" / h3_video.run_id / f"{h3_video.id}-ambience.wav"
        published_path, digest = self._publish_or_reuse(temp_path, final_path)
        asset = self._append_or_get_asset(
            AssetVersion(
                id=f"audio-ambience-{sha256(f'{h3_video.id}:{digest}'.encode()).hexdigest()[:16]}",
                project_id=h3_video.project_id,
                run_id=h3_video.run_id,
                shot_id=h3_video.shot_id,
                parent_id=h3_video.id,
                kind="ambience_audio",
                state="approved",
                path=published_path,
                sha256=digest,
                metadata={
                    "source_asset_id": h3_video.id,
                    "audio_present": True,
                    "validation": {"duration_seconds": duration, "mean_volume_db": mean_volume},
                    "ffmpeg_map": "0:a:0?",
                },
            )
        )
        return AudioClip(
            id=f"ambience-{asset.id}",
            kind="ambience",
            path=asset.path,
            start_seconds=0.0,
            duration_seconds=duration,
            source_asset_id=h3_video.id,
            line_version_id=None,
            text="",
            audio_present=True,
            asset_id=asset.id,
        )

    async def _render_text_clip(
        self,
        *,
        run_id: str,
        shot_id: str,
        kind: Literal["dialogue", "narration"],
        text: str,
        line_version_id: str,
        profile: VoiceProfile,
        start_seconds: float,
    ) -> AudioClip:
        run = self.repo.get_run(run_id)
        if run is None:
            raise KeyError(f"run {run_id} does not exist")
        project = self.repo.get_project(run.project_id)
        if project is None:
            raise KeyError(f"project {run.project_id} does not exist")
        temp_path = self._temp_path(run_id, shot_id, kind, ".wav")
        synthesized = await self.provider.synthesize(text, profile, temp_path)
        if synthesized != temp_path:
            if not synthesized.is_file():
                raise AudioValidationError("voice provider did not create audio")
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(synthesized, temp_path)
        duration, mean_volume = self._validate_audio(temp_path)
        final_name = f"{shot_id}-{kind}-{self._safe_id(line_version_id)}.wav"
        final_path = project.root / "audio" / run_id / final_name
        published_path, digest = self._publish_or_reuse(temp_path, final_path)
        asset = self._append_or_get_asset(
            AssetVersion(
                id=f"audio-{kind}-{sha256(f'{run_id}:{shot_id}:{line_version_id}:{digest}'.encode()).hexdigest()[:16]}",
                project_id=project.id,
                run_id=run_id,
                shot_id=shot_id,
                kind=f"{kind}_audio",
                state="approved",
                path=published_path,
                sha256=digest,
                metadata={
                    "text": text,
                    "line_version_id": line_version_id,
                    "voice_profile": {
                        "voice": profile.voice,
                        "emotion": profile.emotion,
                        "rate": profile.rate,
                        "pitch": profile.pitch,
                        "reference_audio": str(profile.reference_audio) if profile.reference_audio else None,
                    },
                    "validation": {"duration_seconds": duration, "mean_volume_db": mean_volume},
                },
            )
        )
        return AudioClip(
            id=f"{kind}-{line_version_id}",
            kind=kind,
            path=asset.path,
            start_seconds=start_seconds,
            duration_seconds=duration,
            source_asset_id=None,
            line_version_id=line_version_id,
            text=text,
            audio_present=True,
            asset_id=asset.id,
        )

    def _validate_audio(self, path: Path) -> tuple[float, float]:
        if not path.is_file() or path.stat().st_size == 0:
            raise AudioValidationError("audio output is missing or empty")
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        duration = float(json.loads(probe.stdout)["format"]["duration"])
        if duration < self.min_duration_seconds:
            raise AudioValidationError("audio output is too short")
        null_sink = "NUL" if _is_windows_path() else "/dev/null"
        volume = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostdin",
                "-i",
                str(path),
                "-af",
                "volumedetect",
                "-f",
                "null",
                null_sink,
            ],
            capture_output=True,
            text=True,
        )
        combined = f"{volume.stdout}\n{volume.stderr}"
        match = re.search(r"mean_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", combined)
        if not match:
            raise AudioValidationError("audio mean volume could not be measured")
        mean_volume = float("-inf") if match.group(1) == "-inf" else float(match.group(1))
        if mean_volume <= self.min_mean_volume_db:
            raise AudioValidationError("audio output is silent")
        return duration, mean_volume

    def _has_audio_stream(self, path: Path) -> bool:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=index",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return bool(json.loads(probe.stdout).get("streams"))

    def _publish_or_reuse(self, temp_path: Path, final_path: Path) -> tuple[Path, str]:
        digest = _sha256_file(temp_path)
        if final_path.exists():
            if _sha256_file(final_path) != digest:
                temp_path.unlink(missing_ok=True)
                raise FileExistsError(f"audio asset destination already exists: {final_path}")
            temp_path.unlink(missing_ok=True)
            return final_path, digest
        return self.asset_store.publish(temp_path, final_path)

    def _append_or_get_asset(self, asset: AssetVersion) -> AssetVersion:
        existing = self.repo.get_asset(asset.id)
        if existing is not None:
            if existing.sha256 == asset.sha256 and existing.path == asset.path:
                return existing
            raise ValueError(f"audio asset id {asset.id} conflicts with an existing asset")
        return self.repo.append_asset(asset)

    def _temp_path(self, run_id: str, shot_id: str, kind: str, suffix: str) -> Path:
        temp_dir = self.work_root / run_id / "staging"
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir / f"{shot_id}-{kind}-{uuid.uuid4().hex}{suffix}"

    def _line_version_id(self, line, shot_id: str, index: int, *, kind: str) -> str:
        existing = str(getattr(line, "version_id", "") or "")
        if existing:
            return existing
        payload = f"{kind}\0{shot_id}\0{index}\0{getattr(line, 'speaker', '')}\0{getattr(line, 'text', '')}"
        return f"{kind}-{sha256(payload.encode('utf-8')).hexdigest()[:16]}"

    def _shot_start_seconds(self, shots, shot_id: str) -> float:
        start = 0.0
        for shot in shots:
            if shot.id == shot_id:
                return start
            start += float(shot.duration_seconds)
        return start

    def _safe_id(self, value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
        return safe or sha256(value.encode("utf-8")).hexdigest()[:16]


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_windows_path() -> bool:
    return Path.cwd().drive != ""
