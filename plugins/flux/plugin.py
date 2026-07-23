"""
AI Manga Studio Pro V1.0 — Flux Image Plugin

Image generation plugin using Flux model via ComfyUI.
Self-contained — plug-and-play with dedicated GPU via ComfyUIManager.
Generates full reproducibility logs for every shot.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict

from loguru import logger

from plugins.base import ImagePlugin
from backend.media_cache import get_cache


class Plugin(ImagePlugin):
    """Flux image generation plugin.

    Uses the existing WorkflowGenerator to build ComfyUI
    workflow JSON, submits to ComfyUI, and returns the
    output image path.
    """

    def __init__(self) -> None:
        self._client = None
        self._generator = None
        self._output_dir = ""

    # ----------------------------------------------------------
    # Plugin Interface
    # ----------------------------------------------------------

    def generate(self, shot: Any) -> str:
        """Generate an image from shot data.

        Args:
            shot: UnifiedShot object.

        Returns:
            Absolute path to generated image.
        """
        self._ensure_initialized()

        # === CACHE CHECK ===
        cache = get_cache()
        cache_key = self._cache_key(shot)
        cached = cache.get(cache_key, "shots", self._cache_meta(shot))
        if cached:
            logger.info(f"FluxPlugin: CACHE HIT {shot.shot_id} → {os.path.basename(cached)}")
            self._log_generation(shot, cached, cache_hit=True, duration=0.0, workflow={})
            return cached

        # === GENERATE ===
        logger.info(f"FluxPlugin: CACHE MISS {shot.shot_id} — generating...")
        t0 = time.time()

        # Mark shot as generating
        shot.mark_generating()
        if shot.json_path:
            shot.to_json_file(shot.json_path)

        # Build workflow
        workflow = self._generator.generate(shot)

        # Submit to ComfyUI (blocking wait)
        result = self._client.submit_workflow(workflow, wait=True)

        if not result:
            raise RuntimeError("ComfyUI returned empty result for Flux generation")

        images = result.get("images", [])
        if not images:
            raise RuntimeError("No output images in ComfyUI result")

        image_path = images[0].get("path", "")
        if not image_path:
            raise RuntimeError("No output image path found")

        duration = time.time() - t0

        # === UPSCALE if resolution was clamped (4K → safe base) ===
        needs_upscale = getattr(shot, "extra", {}).get("_needs_upscale", False)
        if needs_upscale:
            target_w = shot.extra.get("_target_width", shot.width)
            target_h = shot.extra.get("_target_height", shot.height)
            logger.info(
                f"FluxPlugin: Upscaling {shot.shot_id} "
                f"from base → {target_w}x{target_h}"
            )
            upscaled_path = self._upscale_image(image_path, target_w, target_h)
            if upscaled_path:
                image_path = upscaled_path
                logger.info(f"FluxPlugin: Upscaled → {image_path}")

        # === WRITE CACHE ===
        cache.cache_shot(
            project_id=getattr(shot, "project_id", "") or "default",
            chapter=getattr(shot, "chapter", 0),
            shot_id=shot.shot_id or f"sh{shot.shot:03d}",
            generated_path=image_path,
            prompt_hash=self._prompt_hash(shot),
        )

        # === GENERATION LOG ===
        self._log_generation(shot, image_path, cache_hit=False, duration=duration, workflow=workflow)

        # Update shot
        shot.mark_success(image=image_path)
        if shot.json_path:
            shot.to_json_file(shot.json_path)

        logger.info(f"FluxPlugin: Generated → {image_path}")
        return image_path

    def check_prerequisites(self) -> bool:
        """Verify Flux model and ComfyUI are available."""
        self._ensure_initialized()

        ok, msg = self._client.check_connection()
        if not ok:
            logger.warning(f"FluxPlugin: ComfyUI not reachable: {msg}")
            return False

        logger.info("FluxPlugin: Prerequisites OK")
        return True

    # ----------------------------------------------------------
    # Cache helpers
    # ----------------------------------------------------------

    @staticmethod
    def _cache_key(shot: Any) -> str:
        """Build a unique cache key from shot fields."""
        project = getattr(shot, "project_id", "") or "default"
        chapter = getattr(shot, "chapter", 0)
        sid = shot.shot_id or f"sh{shot.shot:03d}"
        return f"{project}/ch{chapter:02d}/{sid}"

    @staticmethod
    def _cache_meta(shot: Any) -> Dict[str, Any]:
        """Build metadata dict for cache lookup."""
        return {
            "project": getattr(shot, "project_id", "") or "default",
            "chapter": getattr(shot, "chapter", 0),
            "shot_id": shot.shot_id or f"sh{shot.shot:03d}",
            "prompt": (getattr(shot, "positive_prompt", "") or "")[:80],
        }

    @staticmethod
    def _prompt_hash(shot: Any) -> str:
        """Hash of the shot's positive prompt."""
        import hashlib
        prompt = getattr(shot, "positive_prompt", "") or ""
        return hashlib.md5(prompt.encode("utf-8")).hexdigest()[:12]

    # ----------------------------------------------------------
    # Internal
    # ----------------------------------------------------------

    def _ensure_initialized(self) -> None:
        """Lazy-init dependencies. Gets ComfyUI client from GPU manager."""
        if self._client is not None:
            return

        from backend.gpu_manager import get_gpu_manager
        from backend.config import get_config
        from backend.workflow_generator import WorkflowGenerator

        config = get_config()
        self._client = get_gpu_manager().get_client("flux")
        self._generator = WorkflowGenerator()
        self._output_dir = (
            config.comfyui.output_dir
            or config.project.output_path
            or ""
        )

    def _upscale_image(self, image_path: str, target_w: int, target_h: int) -> str:
        """Upscale an image to target resolution using PIL Lanczos + sharpening.

        Uses Lanczos for scaling then applies UnsharpMask to restore
        crispness — mitigating the blur/softness introduced by simple
        interpolation upscaling.

        Args:
            image_path: Path to the generated base image.
            target_w: Target width.
            target_h: Target height.

        Returns:
            Path to the upscaled image, or empty string on failure.
        """
        try:
            from PIL import Image, ImageFilter

            img = Image.open(image_path)
            current_w, current_h = img.size

            # Skip if already at target size
            if current_w >= target_w and current_h >= target_h:
                logger.info(
                    f"FluxPlugin: Skip upscale — image already "
                    f"{current_w}x{current_h} >= {target_w}x{target_h}"
                )
                return image_path

            # Upscale with Lanczos
            img_upscaled = img.resize((target_w, target_h), Image.LANCZOS)

            # Sharpen to counteract Lanczos blur
            # UnsharpMask(radius, percent, threshold) — mild sharpen for 2-4x upscale
            upscale_factor = max(target_w / current_w, target_h / current_h)
            if upscale_factor >= 3.0:
                # Stronger sharpening for large upscale ratios
                img_upscaled = img_upscaled.filter(
                    ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=2)
                )
            elif upscale_factor >= 2.0:
                img_upscaled = img_upscaled.filter(
                    ImageFilter.UnsharpMask(radius=1.2, percent=100, threshold=2)
                )
            else:
                img_upscaled = img_upscaled.filter(
                    ImageFilter.UnsharpMask(radius=0.8, percent=80, threshold=3)
                )

            # Save alongside original with _4k suffix
            base, ext = os.path.splitext(image_path)
            upscaled_path = f"{base}_4k{ext}"
            img_upscaled.save(upscaled_path, quality=95)
            logger.info(
                f"FluxPlugin: Upscaled {current_w}x{current_h} → "
                f"{target_w}x{target_h} (+ UnsharpMask sharpen) → {upscaled_path}"
            )
            return upscaled_path

        except Exception as e:
            logger.error(f"FluxPlugin: Upscale failed for {image_path}: {e}")
            return image_path  # Fall back to base image

    def _log_generation(
        self,
        shot: Any,
        output_path: str,
        cache_hit: bool,
        duration: float,
        workflow: Dict[str, Any],
    ) -> None:
        """Write a full reproducibility log for this generation."""
        from backend.generation_log import GenerationLog
        from backend.gpu_manager import get_gpu_manager

        gpu = get_gpu_manager().get_gpu_info("flux")

        log = GenerationLog(
            shot_id=getattr(shot, "shot_id", "") or "",
            project_id=getattr(shot, "project_id", "") or "",
            chapter=getattr(shot, "chapter", 0),
            scene_num=getattr(shot, "scene_num", 0),
            shot_num=getattr(shot, "shot_num", 0),
            category="image",
            # Prompt
            positive_prompt=getattr(shot, "positive_prompt", "") or "",
            negative_prompt=getattr(shot, "negative_prompt", "") or "",
            # Params (workflow dict captures seed / CFG / sampler / steps / model)
            seed=self._extract_seed(workflow),
            cfg_scale=float(workflow.get("cfg", 7.0)),
            sampler=str(workflow.get("sampler", "euler_ancestral")),
            scheduler=str(workflow.get("scheduler", "normal")),
            steps=int(workflow.get("steps", 30)),
            model=str(workflow.get("model", workflow.get("checkpoint", "Flux"))),
            lora=list(workflow.get("lora", [])),
            width=int(workflow.get("width", 1920)),
            height=int(workflow.get("height", 1080)),
            # GPU
            gpu_id=gpu.get("gpu_id", 0) if gpu else 0,
            gpu_name=gpu.get("name", "") if gpu else "",
            # Timing
            duration_seconds=duration,
            # Output
            output_path=output_path,
            # Cache
            cache_hit=cache_hit,
            # Extra
            weather=getattr(shot, "weather", "") or "",
            time_of_day=getattr(shot, "time_of_day", "") or "",
            camera=getattr(shot, "camera", "") or "",
            emotion=getattr(shot, "emotion", "") or "",
        )

        log.save()
        logger.info(f"FluxPlugin: Logged → seed={log.seed} CFG={log.cfg_scale} {log.sampler} | {log.duration_seconds:.1f}s GPU{log.gpu_id}")

    @staticmethod
    def _extract_seed(workflow: Dict[str, Any]) -> int:
        """Extract seed from workflow dict (may be nested)."""
        seed = workflow.get("seed", -1)
        if seed == -1:
            seed = workflow.get("noise", {}).get("seed", -1)
        if seed == -1:
            seed = workflow.get("sampler_params", {}).get("seed", -1)
        if seed == -1:
            # random seed — peek from ComfyUI globals
            seed = workflow.get("generated_seed", -1)
        return int(seed)
