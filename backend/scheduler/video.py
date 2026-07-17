"""
Scheduler — Video Generation (I2V)

Stage 5: Generate video from static shot images via ComfyUI AnimateDiff.
Only processes shots that have a successful image output.

Flow:
  Python loads shot JSON → checks image exists
  → Python builds I2V workflow → ComfyUI generates video
  → Python saves video path to JSON
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from loguru import logger

from backend.unified_shot import UnifiedShot, ShotStatus
from backend.config import get_config
from plugins import get_registry


@dataclass
class VideoShotResult:
    """Result of one video generation."""
    shot_id: str
    json_path: str = ""
    video_path: str = ""
    status: ShotStatus = ShotStatus.waiting
    attempts: int = 0
    elapsed: float = 0.0
    error: str = ""


@dataclass
class VideoStageResult:
    """Aggregated video generation result."""
    shots: List[VideoShotResult] = field(default_factory=list)
    total: int = 0
    success: int = 0
    failed: int = 0
    elapsed: float = 0.0


class VideoStage:
    """Generate I2V videos via Wan plugin on GPU 1."""

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

    def generate_all(
        self,
        shots: List[UnifiedShot],
        on_shot: Optional[Callable[[VideoShotResult], None]] = None,
    ) -> VideoStageResult:
        """Generate videos for all shots that have valid image outputs.

        Args:
            shots: List of UnifiedShot objects (must have image_path set).
            on_shot: Callback for real-time progress.

        Returns:
            VideoStageResult.
        """
        start = time.time()

        # Only process shots with valid images
        valid = [s for s in shots if s.status == ShotStatus.success and s.image_path]
        result = VideoStageResult(total=len(valid))

        logger.info(f"VideoStage: {len(valid)} shots ready for I2V")

        for i, shot in enumerate(valid):
            logger.info(f"VideoStage: [{i+1}/{len(valid)}] {shot.shot_id}")

            vr = self._generate_one(shot)
            result.shots.append(vr)
            if vr.status == ShotStatus.success:
                result.success += 1
            else:
                result.failed += 1

            if on_shot:
                on_shot(vr)

        result.elapsed = time.time() - start
        logger.info(
            f"VideoStage: Done — {result.success}/{result.total} videos "
            f"in {result.elapsed:.0f}s"
        )
        return result

    def _generate_one(self, shot: UnifiedShot) -> VideoShotResult:
        """Generate one video from a shot's image. Delegates to I2V plugin."""
        start = time.time()

        for attempt in range(1, self.max_retries + 1):
            try:
                config = get_config()
                registry = get_registry()
                plugin = registry.get_video_plugin(config.plugins.video)

                # Plugin handles: workflow → ComfyUI → video_path
                video_path = plugin.generate(shot, shot.image_path)

                # Python: update JSON
                shot.video_path = video_path
                if shot.json_path:
                    shot.to_json_file(shot.json_path)

                return VideoShotResult(
                    shot_id=shot.shot_id or f"sh{shot.shot:03d}",
                    json_path=shot.json_path,
                    video_path=video_path,
                    status=ShotStatus.success,
                    attempts=attempt,
                    elapsed=time.time() - start,
                )

            except Exception as e:
                logger.warning(
                    f"VideoStage: {shot.shot_id} attempt {attempt}/{self.max_retries} failed: {e}"
                )
                if attempt >= self.max_retries:
                    return VideoShotResult(
                        shot_id=shot.shot_id,
                        json_path=shot.json_path,
                        status=ShotStatus.failed,
                        attempts=attempt,
                        elapsed=time.time() - start,
                        error=str(e),
                    )
                time.sleep(2)

        return VideoShotResult(
            shot_id=shot.shot_id,
            status=ShotStatus.failed,
            elapsed=time.time() - start,
        )
