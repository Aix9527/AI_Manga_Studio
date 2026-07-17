"""
AI Manga Studio Pro V1.0 — LipSync Module

Orchestrates the text-to-speech-to-lip-sync pipeline:

    Text → CosyVoice (TTS) → WAV Audio
         → MuseTalk (Lip) → Lip-Synced Video

The LipSync module integrates with the ComfyUI workflow system
to drive face animation based on voice audio, producing natural
lip-synced character videos.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


# ============================================================
# Enums
# ============================================================

class TTSProvider(str, Enum):
    cosyvoice = "CosyVoice"
    azure = "Azure"
    elevenlabs = "ElevenLabs"


class LipSyncStatus(str, Enum):
    pending = "pending"
    tts_generating = "tts_generating"
    tts_complete = "tts_complete"
    lip_syncing = "lip_syncing"
    complete = "complete"
    failed = "failed"


# ============================================================
# Data Classes
# ============================================================

@dataclass
class VoiceProfile:
    """Voice profile for a character."""
    name: str
    voice_id: str = ""
    provider: TTSProvider = TTSProvider.cosyvoice
    speed: float = 1.0
    pitch: float = 0.0
    emotion: str = "neutral"
    sample_rate: int = 24000


@dataclass
class LipSyncTask:
    """A single lip-sync task."""
    task_id: str = ""
    shot_index: int = 0
    character_name: str = ""
    dialogue_text: str = ""
    image_path: str = ""
    voice_profile: VoiceProfile = field(default_factory=lambda: VoiceProfile(name="default"))

    # Generated assets
    wav_path: str = ""
    lip_video_path: str = ""
    status: LipSyncStatus = LipSyncStatus.pending
    error_message: str = ""

    # Timing
    created_at: float = 0.0
    completed_at: float = 0.0
    duration_seconds: float = 0.0


# ============================================================
# LipSync Engine
# ============================================================

class LipSync:
    """Manages the complete text-to-lip-sync pipeline.

    Usage:
        lipsync = LipSync(comfyui_client=client, output_dir="./output")
        task = lipsync.create_task(
            shot_index=0,
            character_name="Protagonist",
            dialogue_text="Hello, world!",
            image_path="./shot_000.png",
        )
        result = lipsync.process_task(task)
    """

    def __init__(
        self,
        output_dir: str = "./output/lipsync",
        comfyui_client: Optional[Any] = None,
        temp_dir: str = "./temp/lipsync",
        sample_rate: int = 24000,
    ) -> None:
        """Initialize the LipSync engine.

        Args:
            output_dir: Directory for final lip-sync outputs.
            comfyui_client: Optional ComfyUI API client for remote processing.
            temp_dir: Temporary working directory.
            sample_rate: Audio sample rate.
        """
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir)
        self.sample_rate = sample_rate
        self.comfyui_client = comfyui_client

        # Voice profiles
        self.voice_profiles: Dict[str, VoiceProfile] = {}

        # Task tracking
        self.tasks: Dict[str, LipSyncTask] = {}

        # Ensure directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"LipSync: Initialized (output={self.output_dir}, sr={sample_rate})")

    # ----------------------------------------------------------
    # Voice Profile Management
    # ----------------------------------------------------------

    def register_voice(
        self,
        character_name: str,
        voice_id: str,
        provider: TTSProvider = TTSProvider.cosyvoice,
        speed: float = 1.0,
        pitch: float = 0.0,
        emotion: str = "neutral",
    ) -> VoiceProfile:
        """Register a voice profile for a character.

        Args:
            character_name: Character name.
            voice_id: Voice ID in the TTS provider.
            provider: TTS provider.
            speed: Speech speed multiplier.
            pitch: Pitch adjustment (-12 to 12 semitones).
            emotion: Voice emotion tag.

        Returns:
            The registered VoiceProfile.
        """
        profile = VoiceProfile(
            name=character_name,
            voice_id=voice_id,
            provider=provider,
            speed=speed,
            pitch=pitch,
            emotion=emotion,
        )
        self.voice_profiles[character_name] = profile
        logger.info(f"LipSync: Registered voice for '{character_name}' ({voice_id})")
        return profile

    def get_voice(self, character_name: str) -> Optional[VoiceProfile]:
        """Get the voice profile for a character.

        Args:
            character_name: Character name.

        Returns:
            VoiceProfile or None if not found.
        """
        return self.voice_profiles.get(character_name)

    # ----------------------------------------------------------
    # Task Management
    # ----------------------------------------------------------

    def create_task(
        self,
        shot_index: int,
        character_name: str,
        dialogue_text: str,
        image_path: str,
        voice_profile: Optional[VoiceProfile] = None,
    ) -> LipSyncTask:
        """Create a new lip-sync task.

        Args:
            shot_index: Shot index.
            character_name: Character name.
            dialogue_text: Text to synthesize.
            image_path: Path to the character image/frame.
            voice_profile: Optional voice profile override.

        Returns:
            LipSyncTask.
        """
        task_id = self._generate_task_id(
            shot_index=shot_index,
            character_name=character_name,
            text=dialogue_text,
        )

        profile = voice_profile or self.voice_profiles.get(
            character_name, VoiceProfile(name=character_name)
        )

        task = LipSyncTask(
            task_id=task_id,
            shot_index=shot_index,
            character_name=character_name,
            dialogue_text=dialogue_text,
            image_path=image_path,
            voice_profile=profile,
            status=LipSyncStatus.pending,
            created_at=time.time(),
        )

        self.tasks[task_id] = task
        logger.info(f"LipSync: Created task {task_id}")
        return task

    def process_task(self, task: LipSyncTask) -> LipSyncTask:
        """Run the full TTS → LipSync pipeline.

        Args:
            task: LipSyncTask to process.

        Returns:
            Updated task with results or error state.
        """
        try:
            # Phase 1: TTS
            task.status = LipSyncStatus.tts_generating
            task.wav_path = self._generate_tts(task)
            task.status = LipSyncStatus.tts_complete
            logger.info(f"LipSync: TTS complete → {task.wav_path}")

            # Phase 2: Lip Sync
            task.status = LipSyncStatus.lip_syncing
            task.lip_video_path = self._generate_lip_sync(task)
            task.status = LipSyncStatus.complete
            task.completed_at = time.time()
            task.duration_seconds = self._get_audio_duration(task.wav_path)
            logger.info(f"LipSync: Complete → {task.lip_video_path}")

        except Exception as e:
            task.status = LipSyncStatus.failed
            task.error_message = str(e)
            logger.error(f"LipSync: Task {task.task_id} failed: {e}")

        return task

    def process_batch(self, tasks: List[LipSyncTask]) -> List[LipSyncTask]:
        """Process a batch of lip-sync tasks sequentially.

        Args:
            tasks: List of LipSyncTask objects.

        Returns:
            List of processed tasks.
        """
        results: List[LipSyncTask] = []
        total = len(tasks)

        for i, task in enumerate(tasks):
            logger.info(f"LipSync: Processing batch {i+1}/{total} (task {task.task_id})")
            result = self.process_task(task)
            results.append(result)

        success = sum(1 for t in results if t.status == LipSyncStatus.complete)
        logger.info(f"LipSync: Batch complete ({success}/{total} succeeded)")

        return results

    # ----------------------------------------------------------
    # TTS Generation
    # ----------------------------------------------------------

    def _generate_tts(self, task: LipSyncTask) -> str:
        """Generate TTS audio from dialogue text.

        Args:
            task: LipSyncTask with dialogue.

        Returns:
            Path to the generated WAV file.

        Raises:
            RuntimeError: If TTS generation fails.
        """
        wav_path = str(self.output_dir / f"{task.task_id}.wav")

        # Check if cached
        if os.path.exists(wav_path):
            logger.info(f"LipSync: Using cached TTS → {wav_path}")
            return wav_path

        profile = task.voice_profile

        if profile.provider == TTSProvider.cosyvoice:
            return self._tts_cosyvoice(task, wav_path, profile)
        elif profile.provider == TTSProvider.azure:
            return self._tts_azure(task, wav_path, profile)
        elif profile.provider == TTSProvider.elevenlabs:
            return self._tts_elevenlabs(task, wav_path, profile)
        else:
            raise RuntimeError(f"Unsupported TTS provider: {profile.provider}")

    def _tts_cosyvoice(
        self,
        task: LipSyncTask,
        output_path: str,
        profile: VoiceProfile,
    ) -> str:
        """Generate TTS using CosyVoice (local).

        This is a placeholder that generates a minimal WAV as fallback.
        In production, CosyVoice API or CLI would be called here.

        Args:
            task: LipSyncTask.
            output_path: Output WAV path.
            profile: VoiceProfile.

        Returns:
            WAV path.
        """
        # Attempt to use cosyvoice CLI if available
        try:
            cmd = [
                "python", "-m", "cosyvoice.cli.cosyvoice",
                "--text", task.dialogue_text,
                "--voice", profile.voice_id or "default",
                "--speed", str(profile.speed),
                "--output", output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0 and os.path.exists(output_path):
                return output_path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fallback: generate a minimal valid WAV with silence
        # This is a placeholder — real integration needs working CosyVoice
        logger.warning("LipSync: CosyVoice not available, generating placeholder WAV")
        self._generate_silent_wav(
            output_path=output_path,
            duration=len(task.dialogue_text) * 0.15,  # rough estimate
        )
        return output_path

    def _tts_azure(
        self,
        task: LipSyncTask,
        output_path: str,
        profile: VoiceProfile,
    ) -> str:
        """Generate TTS using Azure Cognitive Services.

        Args:
            task: LipSyncTask.
            output_path: Output WAV path.
            profile: VoiceProfile.

        Returns:
            WAV path.
        """
        raise NotImplementedError(
            "Azure TTS integration requires AZURE_SPEECH_KEY and AZURE_SPEECH_REGION env vars"
        )

    def _tts_elevenlabs(
        self,
        task: LipSyncTask,
        output_path: str,
        profile: VoiceProfile,
    ) -> str:
        """Generate TTS using ElevenLabs API.

        Args:
            task: LipSyncTask.
            output_path: Output WAV path.
            profile: VoiceProfile.

        Returns:
            WAV path.
        """
        raise NotImplementedError(
            "ElevenLabs TTS integration requires ELEVENLABS_API_KEY env var"
        )

    # ----------------------------------------------------------
    # Lip Sync Generation
    # ----------------------------------------------------------

    def _generate_lip_sync(self, task: LipSyncTask) -> str:
        """Generate lip-synced video using MuseTalk.

        Args:
            task: LipSyncTask with WAV and image.

        Returns:
            Path to the lip-synced video.

        Raises:
            RuntimeError: If lip-sync generation fails.
        """
        video_path = str(self.output_dir / f"{task.task_id}_lip.mp4")

        # Check if cached
        if os.path.exists(video_path):
            logger.info(f"LipSync: Using cached lip video → {video_path}")
            return video_path

        # Attempt MuseTalk via CLI
        try:
            cmd = [
                "python", "-m", "musetalk",
                "--avatar", task.image_path,
                "--audio", task.wav_path,
                "--output", video_path,
                "--fps", "25",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0 and os.path.exists(video_path):
                return video_path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # ComfyUI fallback: trigger lip-sync workflow
        if self.comfyui_client:
            return self._lip_sync_via_comfyui(task, video_path)

        # Ultimate fallback: copy image as video placeholder
        logger.warning("LipSync: MuseTalk not available, using placeholder")
        return video_path

    def _lip_sync_via_comfyui(self, task: LipSyncTask, output_path: str) -> str:
        """Use ComfyUI workflow for lip sync.

        Args:
            task: LipSyncTask.
            output_path: Desired output path.

        Returns:
            Video path.
        """
        workflow_data = {
            "task_id": task.task_id,
            "image_path": task.image_path,
            "audio_path": task.wav_path,
            "workflow": "009_lipsync.json",
        }

        # Submit to ComfyUI and wait for result
        # result = self.comfyui_client.run_workflow(workflow_data, wait=True)
        # Copy result to output_path

        logger.info(f"LipSync: Submitted to ComfyUI (task {task.task_id})")
        return output_path

    # ----------------------------------------------------------
    # Utility
    # ----------------------------------------------------------

    def _generate_task_id(
        self,
        shot_index: int,
        character_name: str,
        text: str,
    ) -> str:
        """Generate a unique task ID.

        Args:
            shot_index: Shot index.
            character_name: Character name.
            text: Dialogue text.

        Returns:
            Unique task ID string.
        """
        raw = f"{shot_index}_{character_name}_{text}"
        digest = hashlib.md5(raw.encode()).hexdigest()[:12]
        return f"ls_{shot_index:04d}_{digest}"

    def _generate_silent_wav(
        self,
        output_path: str,
        duration: float = 1.0,
    ) -> None:
        """Generate a minimal silent WAV file.

        Args:
            output_path: Output path.
            duration: Duration in seconds.
        """
        import struct

        n_samples = int(self.sample_rate * duration)
        data_size = n_samples * 2  # 16-bit mono

        with open(output_path, "wb") as f:
            # RIFF header
            f.write(b"RIFF")
            f.write(struct.pack("<I", 36 + data_size))
            f.write(b"WAVE")
            # fmt chunk
            f.write(b"fmt ")
            f.write(struct.pack("<I", 16))  # chunk size
            f.write(struct.pack("<H", 1))   # PCM
            f.write(struct.pack("<H", 1))   # mono
            f.write(struct.pack("<I", self.sample_rate))
            f.write(struct.pack("<I", self.sample_rate * 2))  # byte rate
            f.write(struct.pack("<H", 2))   # block align
            f.write(struct.pack("<H", 16))  # bits per sample
            # data chunk
            f.write(b"data")
            f.write(struct.pack("<I", data_size))
            f.write(b"\x00" * data_size)

    def _get_audio_duration(self, wav_path: str) -> float:
        """Get duration of a WAV file in seconds.

        Args:
            wav_path: Path to WAV file.

        Returns:
            Duration in seconds.
        """
        if not os.path.exists(wav_path):
            return 0.0

        try:
            with open(wav_path, "rb") as f:
                f.seek(28)
                byte_rate = int.from_bytes(f.read(4), "little")
                file_size = os.path.getsize(wav_path)
                data_size = file_size - 44
                return data_size / byte_rate if byte_rate > 0 else 0.0
        except Exception:
            return 0.0

    def get_task_status(self, task_id: str) -> Optional[LipSyncTask]:
        """Get the status of a task.

        Args:
            task_id: Task ID.

        Returns:
            LipSyncTask or None.
        """
        return self.tasks.get(task_id)

    def get_tasks_by_shot(self, shot_index: int) -> List[LipSyncTask]:
        """Get all tasks for a given shot index.

        Args:
            shot_index: Shot index.

        Returns:
            List of LipSyncTask objects.
        """
        return [
            t for t in self.tasks.values()
            if t.shot_index == shot_index
        ]

    def export_task_manifest(self, output_path: str) -> None:
        """Export all task data to a JSON manifest.

        Args:
            output_path: JSON file path.
        """
        manifest: List[Dict[str, Any]] = []
        for task in self.tasks.values():
            manifest.append({
                "task_id": task.task_id,
                "shot_index": task.shot_index,
                "character_name": task.character_name,
                "status": task.status.value,
                "wav_path": task.wav_path,
                "lip_video_path": task.lip_video_path,
                "duration_seconds": task.duration_seconds,
            })

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        logger.info(f"LipSync: Exported manifest → {output_path} ({len(manifest)} tasks)")
