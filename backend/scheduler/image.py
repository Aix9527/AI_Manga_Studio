"""
Scheduler — Shot Image Composition

Stage 4: The core pipeline stage. For each shot:
  1. Python loads UnifiedShot JSON
  2. Python assembles prompt from shot fields
  3. Python builds ComfyUI workflow JSON
  4. → Submit to ComfyUI (GPU inference only)
  5. Wait for completion
  6. Python saves output path to shot JSON
  7. Python saves to database
  → Next shot
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
class ImageShotResult:
    """Result of one shot image generation."""
    shot_id: str
    json_path: str = ""
    image_path: str = ""
    status: ShotStatus = ShotStatus.waiting
    attempts: int = 0
    elapsed: float = 0.0
    error: str = ""


@dataclass
class ImageStageResult:
    """Aggregated image generation result."""
    shots: List[ImageShotResult] = field(default_factory=list)
    total: int = 0
    success: int = 0
    failed: int = 0
    elapsed: float = 0.0


class ImageStage:
    """Generate images for all shots via plugin system.

    Each plugin gets its dedicated GPU via ComfyUIManager.
    Flux → GPU 0, no cross-talk.

    Loop: load JSON → plugin generate → save → next.
    """

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

        # Rate limiting
        self._last_submit_at: float = 0.0
        self._min_interval: float = 1.0  # seconds between submissions

    def generate_all(
        self,
        shot_paths: List[str],
        on_shot: Optional[Callable[[ImageShotResult], None]] = None,
    ) -> ImageStageResult:
        """Generate images for all shots in order.

        Args:
            shot_paths: List of absolute paths to shot_xxx.json files.
            on_shot: Callback for real-time progress.

        Returns:
            ImageStageResult.
        """
        start = time.time()
        result = ImageStageResult(total=len(shot_paths))

        for i, sp in enumerate(shot_paths):
            logger.info(f"ImageStage: [{i+1}/{len(shot_paths)}] {sp}")

            try:
                shot = UnifiedShot.from_json_file(sp)
                sr = self._generate_one(shot)

                result.shots.append(sr)
                if sr.status == ShotStatus.success:
                    result.success += 1
                else:
                    result.failed += 1

                if on_shot:
                    on_shot(sr)

            except Exception as e:
                logger.error(f"ImageStage: Failed to process {sp}: {e}")
                result.failed += 1
                result.shots.append(ImageShotResult(
                    shot_id=sp, status=ShotStatus.failed, error=str(e)
                ))

        result.elapsed = time.time() - start
        logger.info(
            f"ImageStage: Done — {result.success}/{result.total} success "
            f"in {result.elapsed:.0f}s"
        )
        return result

    def _generate_one(self, shot: UnifiedShot) -> ImageShotResult:
        """Generate one shot image with quality evaluation.

        Pipeline:
          1. Plugin generates image
          2. Quality Engine evaluates (Python side, NOT ComfyUI)
          3. If FAIL: mutate params → re-generate → evaluate again
          4. If PASS (or max retries): save result

        Failed shots are auto re-queued — zero human intervention.
        """
        start = time.time()

        from backend.quality_engine import get_quality_engine

        qe = get_quality_engine()
        config = get_config()
        registry = get_registry()
        plugin = registry.get_image_plugin(config.plugins.image)

        for attempt in range(1, self.max_retries + 1):
            try:
                # Rate limit
                elapsed_since_last = time.time() - self._last_submit_at
                if elapsed_since_last < self._min_interval:
                    time.sleep(self._min_interval - elapsed_since_last)

                # Plugin handles: mark_generating → workflow → ComfyUI → image_path
                image_path = plugin.generate(shot)
                self._last_submit_at = time.time()

                # === QUALITY EVALUATION (Python side, independent of ComfyUI) ===
                qr = qe.evaluate(shot, image_path)
                if not qr.passed:
                    logger.warning(
                        f"ImageStage: Quality FAIL for {shot.shot_id} — "
                        f"attempt {attempt}/{self.max_retries} — {qr.failure_summary}"
                    )
                    if attempt < self.max_retries:
                        # Mutation happens inside plugin on next call (seed bump via generate)
                        continue
                    # Max retries — accept best-effort result anyway
                    logger.error(
                        f"ImageStage: Max retries exhausted for {shot.shot_id}. "
                        f"Accepting best-effort: {image_path}"
                    )

                # Python: update JSON + DB
                shot.mark_success(image=image_path)
                if shot.json_path:
                    shot.to_json_file(shot.json_path)

                return ImageShotResult(
                    shot_id=shot.shot_id or f"sh{shot.shot:03d}",
                    json_path=shot.json_path,
                    image_path=image_path,
                    status=ShotStatus.success,
                    attempts=attempt,
                    elapsed=time.time() - start,
                )

            except Exception as e:
                logger.warning(
                    f"ImageStage: {shot.shot_id} attempt {attempt}/{self.max_retries} failed: {e}"
                )
                if attempt >= self.max_retries:
                    shot.mark_failed(str(e))
                    if shot.json_path:
                        shot.to_json_file(shot.json_path)
                    return ImageShotResult(
                        shot_id=shot.shot_id or f"sh{shot.shot:03d}",
                        json_path=shot.json_path,
                        status=ShotStatus.failed,
                        attempts=attempt,
                        elapsed=time.time() - start,
                        error=str(e),
                    )
                time.sleep(2)

        return ImageShotResult(
            shot_id=shot.shot_id,
            status=ShotStatus.failed,
            elapsed=time.time() - start,
        )
