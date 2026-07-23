"""
AI Manga Studio Pro V1.0 — Wan Video Plugin

I2V plugin using Wan model via ComfyUI.
Self-contained — plug-and-play with dedicated GPU via ComfyUIManager.
Generates full reproducibility logs for every generation.
"""

from __future__ import annotations

import time
from typing import Any, Dict

from loguru import logger

from plugins.base import VideoPlugin


class Plugin(VideoPlugin):
    """Wan video generation plugin (I2V).

    Converts a still image to animated video using the Wan
    model pipeline in ComfyUI.
    """

    def __init__(self) -> None:
        self._client = None
        self._generator = None

    # ----------------------------------------------------------
    # Plugin Interface
    # ----------------------------------------------------------

    def generate(self, shot: Any, image_path: str) -> str:
        """Generate video from image.

        Args:
            shot: UnifiedShot with motion/duration metadata.
            image_path: Path to source still image.

        Returns:
            Absolute path to generated video file.
        """
        self._ensure_initialized()
        t0 = time.time()

        # Build I2V workflow
        workflow = self._generator.generate(shot, image_path)

        # Submit to ComfyUI (blocking wait)
        result = self._client.submit_workflow(workflow, wait=True)

        if not result:
            raise RuntimeError("ComfyUI returned empty result for Wan I2V")

        videos = result.get("videos", [])
        images = result.get("images", [])

        video_path = ""
        if videos:
            video_path = videos[0].get("path", "") or videos[0].get("filename", "")
        elif images:
            # AnimateDiff may output as image sequence
            video_path = images[0].get("path", "")

        if not video_path:
            raise RuntimeError("No output video path found")

        duration = time.time() - t0
        self._log_generation(shot, video_path, duration, workflow)

        logger.info(f"WanPlugin: Generated → {video_path}")
        return video_path

    def check_prerequisites(self) -> bool:
        """Verify Wan model and ComfyUI are available."""
        self._ensure_initialized()

        ok, msg = self._client.check_connection()
        if not ok:
            logger.warning(f"WanPlugin: ComfyUI not reachable: {msg}")
            return False

        logger.info("WanPlugin: Prerequisites OK")
        return True

    # ----------------------------------------------------------
    # Internal
    # ----------------------------------------------------------

    def _ensure_initialized(self) -> None:
        """Lazy-init dependencies. Gets ComfyUI client from GPU manager."""
        if self._client is not None:
            return

        from backend.gpu_manager import get_gpu_manager
        from backend.i2v_generator import I2VGenerator

        self._client = get_gpu_manager().get_client("wan")
        self._generator = I2VGenerator()

    def _log_generation(
        self, shot: Any, output_path: str, duration: float, workflow: Dict[str, Any]
    ) -> None:
        """Write a full reproducibility log for this I2V generation."""
        from backend.generation_log import GenerationLog
        from backend.gpu_manager import get_gpu_manager

        gpu = get_gpu_manager().get_gpu_info("wan")

        log = GenerationLog(
            shot_id=getattr(shot, "shot_id", "") or "",
            project_id=getattr(shot, "project_id", "") or "",
            chapter=getattr(shot, "chapter", 0),
            scene_num=getattr(shot, "scene_num", 0),
            shot_num=getattr(shot, "shot_num", 0),
            category="video",
            positive_prompt=getattr(shot, "positive_prompt", "") or "",
            negative_prompt=getattr(shot, "negative_prompt", "") or "",
            seed=int(workflow.get("seed", -1)),
            cfg_scale=float(workflow.get("cfg", 7.0)),
            sampler=str(workflow.get("sampler", "euler_ancestral")),
            scheduler=str(workflow.get("scheduler", "normal")),
            steps=int(workflow.get("steps", 20)),
            model=str(workflow.get("model", "Wan")),
            lora=list(workflow.get("lora", [])),
            width=int(workflow.get("width", 1920)),
            height=int(workflow.get("height", 1080)),
            gpu_id=gpu.get("gpu_id", 1) if gpu else 1,
            gpu_name=gpu.get("name", "") if gpu else "",
            duration_seconds=duration,
            output_path=output_path,
            cache_hit=False,
            weather=getattr(shot, "weather", "") or "",
            time_of_day=getattr(shot, "time_of_day", "") or "",
            camera=getattr(shot, "camera", "") or "",
            emotion=getattr(shot, "emotion", "") or "",
        )

        log.save()
        logger.info(f"WanPlugin: Logged → seed={log.seed} | {log.duration_seconds:.1f}s GPU{log.gpu_id}")
