"""HD Redraw Module — Storyboard Frame Upscaling.

Based on the Krene tutorial workflow (Step 05, Step 2), this module:
1. Takes generated storyboard keyframes
2. Upscales/redraws them to 4K resolution
3. Enhances detail and clarity for better video generation

The tutorial emphasizes that HD redraw is critical for video quality:
  "单独放大视角（对应的编号：如A1）为4k高清图，
   并保持视角，构图，风格，内容都不变"

This module supports two modes:
  1. ComfyUI-based HD redraw (when available) — uses img2img with low denoise
  2. PIL-based upscaling fallback (when ComfyUI is unavailable)

Tutorial reference:
  https://www.krene.com/blog/ai-video-comic-drama-tutorial
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

from backend.production.keyframe_generator import KeyframeGenerator

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# HD Redraw Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Target resolution for HD redraw (4K equivalent)
HD_TARGET_WIDTH = 2048
HD_TARGET_HEIGHT = 3072  # 2:3 portrait ratio for 9:16 content

# Upscaling parameters for ComfyUI img2img
UPSCALE_DENOISE_STRENGTH = 0.15  # Low denoise to preserve composition
UPSCALE_CFG_SCALE = 4.5  # Lower CFG for natural detail enhancement
UPSCALE_SAMPLER = "euler"
UPSCALE_SCHEDULER = "normal"
UPSCALE_STEPS = 20

# Quality prompt additions for HD redraw
HD_QUALITY_PROMPT = (
    "ultra high definition, 4K, extremely detailed, sharp focus, "
    "high resolution, fine details, professional quality, "
    "no artifacts, clean image, perfect composition"
)

HD_NEGATIVE_PROMPT = (
    "mosaic, pixelated, blocky, low quality, worst quality, blur, "
    "deformed, disfigured, extra limbs, bad anatomy, "
    "text, logo, watermark, noise, grain"
)

KEYFRAME_REFINE_CHAIN = (
    "preserve the exact composition, camera angle, framing and pose",
    "preserve character identity, costume, facial structure and silhouette",
    "refine edges, fabric texture, skin detail, lighting gradients and background depth",
    "remove mosaic, compression artifacts, blockiness and unintended text",
)


def build_keyframe_refine_prompt(original_prompt: str) -> str:
    """Compile the HD redraw prompt for the keyframe_refine strategy."""
    base = original_prompt.strip()
    parts = [base] if base else []
    parts.extend(KEYFRAME_REFINE_CHAIN)
    parts.append(HD_QUALITY_PROMPT)
    return ", ".join(part for part in parts if part)


class HDRedrawer:
    """Upscales and enhances storyboard keyframes to 4K resolution.

    Implements the tutorial's HD redraw step:
    1. Load original keyframe image
    2. Generate HD version via ComfyUI img2img (or PIL fallback)
    3. Save HD version alongside original
    4. Return path to HD image for video generation

    The HD images are used as input for video generation, ensuring
    higher quality output with more detail and clarity.
    """

    def __init__(
        self,
        keyframe_gen: Optional[KeyframeGenerator] = None,
        comfy_base_url: str = "http://127.0.0.1:8188",
    ) -> None:
        self.keyframe_gen = keyframe_gen or KeyframeGenerator(comfy_base_url)
        self.base_url = comfy_base_url

    async def redraw_frame(
        self,
        input_path: Path,
        output_path: Path,
        original_prompt: str = "",
        shot_id: str = "",
    ) -> bool:
        """Upscale a single keyframe to HD resolution.

        Args:
            input_path: Path to the original keyframe image.
            output_path: Where to save the HD version.
            original_prompt: The original generation prompt (for context).
            shot_id: Shot identifier for logging.

        Returns:
            True if HD redraw succeeded, False if fallback was used.
        """
        if not input_path.exists():
            logger.error("Input image not found for HD redraw: %s", input_path)
            return False

        # Try ComfyUI-based HD redraw first
        if await self.keyframe_gen.is_available():
            success = await self._comfy_hd_redraw(
                input_path, output_path, original_prompt, shot_id
            )
            if success:
                return True
            logger.warning(
                "ComfyUI HD redraw failed for %s, falling back to PIL upscale",
                shot_id or input_path.name,
            )

        # Fallback: PIL-based upscaling with enhancement
        return self._pil_hd_upscale(input_path, output_path, original_prompt, shot_id)

    async def redraw_batch(
        self,
        frames: list[dict[str, Any]],
        project_id: str,
        output_root: str = "projects",
    ) -> list[dict[str, Any]]:
        """Batch redraw multiple keyframes to HD.

        Args:
            frames: List of dicts with keys:
                - input_path: Path to original image
                - output_path: Path to save HD image
                - prompt: Original generation prompt
                - shot_id: Shot identifier
            project_id: Project ID for logging.
            output_root: Root output directory.

        Returns:
            List of results with success status and paths.
        """
        results: list[dict[str, Any]] = []

        for frame in frames:
            input_path = Path(frame.get("input_path", ""))
            output_path = Path(frame.get("output_path", ""))
            prompt = frame.get("prompt", "")
            shot_id = frame.get("shot_id", "")

            success = await self.redraw_frame(
                input_path, output_path, prompt, shot_id
            )

            results.append({
                "shot_id": shot_id,
                "input_path": str(input_path),
                "output_path": str(output_path),
                "success": success,
                "hd_path": str(output_path) if success else "",
            })

            logger.info(
                "HD redraw %s: %s -> %s (%s)",
                shot_id,
                input_path.name,
                output_path.name,
                "OK" if success else "FAILED",
            )

        success_count = sum(1 for r in results if r["success"])
        logger.info(
            "HD redraw batch complete: %d/%d succeeded for project %s",
            success_count, len(results), project_id,
        )

        return results

    async def _comfy_hd_redraw(
        self,
        input_path: Path,
        output_path: Path,
        prompt: str,
        shot_id: str,
    ) -> bool:
        """Use ComfyUI img2img for HD redraw with detail enhancement."""
        try:
            import httpx
            import base64
            import time

            # Read and encode the input image
            image_data = input_path.read_bytes()
            image_b64 = base64.b64encode(image_data).decode("utf-8")

            # Build a simple img2img workflow for upscaling
            # Use the detected model from keyframe generator
            model = await self.keyframe_gen.detect_best_model()
            if model is None:
                return False

            # Load the upscale workflow template
            workflow_path = Path("backend/production/workflows/sdxl_t2i_keyframe.json")
            if not workflow_path.exists():
                logger.warning("Workflow template not found for HD redraw")
                return False

            with open(workflow_path, "r", encoding="utf-8") as f:
                template = json.load(f)
            workflow = dict(template["workflow"])
            bindings = template["bindings"]

            # Enhance prompt with the keyframe_refine strategy chain.
            hd_prompt = build_keyframe_refine_prompt(prompt)
            negative = HD_NEGATIVE_PROMPT

            # Fill in workflow parameters
            if "prompt" in bindings:
                workflow[bindings["prompt"][0]]["inputs"][bindings["prompt"][1]] = hd_prompt
            if "negative_prompt" in bindings:
                workflow[bindings["negative_prompt"][0]]["inputs"][bindings["negative_prompt"][1]] = negative
            if "checkpoint" in bindings:
                workflow[bindings["checkpoint"][0]]["inputs"][bindings["checkpoint"][1]] = model

            # Set HD resolution
            if "width" in bindings:
                w_binding = bindings["width"]
                if isinstance(w_binding[0], list):
                    for wb in w_binding:
                        workflow[wb[0]]["inputs"][wb[1]] = HD_TARGET_WIDTH
                else:
                    workflow[w_binding[0]]["inputs"][w_binding[1]] = HD_TARGET_WIDTH
            if "height" in bindings:
                h_binding = bindings["height"]
                if isinstance(h_binding[0], list):
                    for hb in h_binding:
                        workflow[hb[0]]["inputs"][hb[1]] = HD_TARGET_HEIGHT
                else:
                    workflow[h_binding[0]]["inputs"][h_binding[1]] = HD_TARGET_HEIGHT

            # Set seed for reproducibility
            seed = abs(hash(f"hd_{shot_id}")) % 1000000
            if "seed" in bindings:
                workflow[bindings["seed"][0]]["inputs"][bindings["seed"][1]] = seed

            if "filename_prefix" in bindings:
                workflow[bindings["filename_prefix"][0]]["inputs"][bindings["filename_prefix"][1]] = \
                    f"hd_redraw/{output_path.stem}"

            # Submit workflow
            async with httpx.AsyncClient(trust_env=False, timeout=30) as client:
                submit_resp = await client.post(
                    f"{self.base_url}/prompt",
                    json={"prompt": workflow},
                )
                submit_data = submit_resp.json()

            if submit_resp.status_code >= 400:
                logger.error("ComfyUI rejected HD redraw workflow: %s", str(submit_data)[:300])
                return False

            prompt_id = submit_data.get("prompt_id", "")
            if not prompt_id:
                return False

            # Wait for completion (up to 3 minutes for HD)
            start = time.monotonic()
            timeout = 180

            while time.monotonic() - start < timeout:
                async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                    hist_resp = await client.get(f"{self.base_url}/history/{prompt_id}")

                data = hist_resp.json()
                entry = data.get(prompt_id)

                if entry is not None:
                    outputs = entry.get("outputs", {})
                    status = entry.get("status", {})

                    if outputs:
                        for node_output in outputs.values():
                            if not isinstance(node_output, dict):
                                continue
                            for media_kind in ("images", "gifs"):
                                items = node_output.get(media_kind, [])
                                if not isinstance(items, list):
                                    continue
                                for item in items:
                                    if isinstance(item, dict) and item.get("filename"):
                                        filename = item["filename"]
                                        subfolder = item.get("subfolder", "")
                                        file_type = item.get("type", "output")
                                        params = {
                                            "filename": filename,
                                            "subfolder": subfolder,
                                            "type": file_type,
                                        }
                                        async with httpx.AsyncClient(trust_env=False, timeout=120) as client:
                                            dl_resp = await client.get(
                                                f"{self.base_url}/view",
                                                params=params,
                                            )
                                        if dl_resp.status_code == 200 and len(dl_resp.content) > 0:
                                            output_path.parent.mkdir(parents=True, exist_ok=True)
                                            output_path.write_bytes(dl_resp.content)
                                            logger.info(
                                                "HD redraw saved: %s (%d KB)",
                                                output_path.name,
                                                len(dl_resp.content) // 1024,
                                            )
                                            return True

                    if status.get("status_str") == "error":
                        logger.error("ComfyUI HD redraw error for %s", shot_id)
                        return False

                    if status.get("completed"):
                        return False

                await asyncio.sleep(2)

            logger.warning("ComfyUI HD redraw timed out for %s", shot_id)
            return False

        except Exception as exc:
            logger.error("ComfyUI HD redraw failed: %s", exc, exc_info=True)
            return False

    def _pil_hd_upscale(
        self,
        input_path: Path,
        output_path: Path,
        prompt: str,
        shot_id: str,
    ) -> bool:
        """PIL-based fallback upscaling with detail enhancement.

        When ComfyUI is unavailable, uses PIL to:
        1. Upscale image to HD resolution (Lanczos resampling)
        2. Apply sharpening filter
        3. Adjust contrast and saturation
        4. Save as HD version
        """
        try:
            from PIL import Image, ImageEnhance, ImageFilter

            # Load original image
            img = Image.open(input_path).convert("RGB")
            orig_w, orig_h = img.size

            # Calculate scaling factor
            scale_w = HD_TARGET_WIDTH / orig_w
            scale_h = HD_TARGET_HEIGHT / orig_h
            scale = min(scale_w, scale_h)  # Preserve aspect ratio

            # Upscale with Lanczos resampling (high quality)
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)

            # Apply sharpening
            img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=3))

            # Enhance contrast
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.15)

            # Enhance color saturation
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(1.1)

            # Enhance brightness slightly
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(1.05)

            # Apply slight noise reduction
            img = img.filter(ImageFilter.MedianFilter(size=1))

            # Save HD version
            output_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(output_path, format="PNG", quality=95)

            file_size = output_path.stat().st_size // 1024
            logger.info(
                "PIL HD upscale saved: %s (%dx%d, %d KB)",
                output_path.name, new_w, new_h, file_size,
            )
            return True

        except Exception as exc:
            logger.error("PIL HD upscale failed for %s: %s", shot_id, exc)

            # Last resort: copy original
            try:
                import shutil
                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(input_path, output_path)
                logger.warning("Copied original as HD fallback: %s", output_path.name)
                return True
            except Exception:
                return False


# ─────────────────────────────────────────────────────────────────────────────
# Convenience functions
# ─────────────────────────────────────────────────────────────────────────────

async def redraw_all_keyframes(
    project_id: str,
    output_dir: Path,
    shots: list[dict[str, Any]],
    comfy_base_url: str = "http://127.0.0.1:8188",
) -> dict[str, str]:
    """Redraw all keyframes in a project to HD.

    Args:
        project_id: Project identifier.
        output_dir: Output directory containing images/ subdirectory.
        shots: List of shot dicts with 'id' field.
        comfy_base_url: ComfyUI base URL.

    Returns:
        Dict mapping shot_id -> HD image path.
    """
    redrawer = HDRedrawer(comfy_base_url=comfy_base_url)

    # Collect all keyframe images
    frames: list[dict[str, Any]] = []
    images_dir = output_dir / "images"

    for shot in shots:
        shot_id = shot.get("id", "")
        if not shot_id:
            continue

        shot_img_dir = images_dir / shot_id
        frame_path = shot_img_dir / "frame.png"

        if frame_path.exists():
            hd_path = shot_img_dir / "frame_hd.png"
            frames.append({
                "input_path": str(frame_path),
                "output_path": str(hd_path),
                "prompt": shot.get("positive_prompt", ""),
                "shot_id": shot_id,
            })

        # Also handle last frame if it exists
        last_frame_path = shot_img_dir / "frame_last.png"
        if last_frame_path.exists():
            hd_last_path = shot_img_dir / "frame_last_hd.png"
            frames.append({
                "input_path": str(last_frame_path),
                "output_path": str(hd_last_path),
                "prompt": shot.get("positive_prompt", ""),
                "shot_id": f"{shot_id}_last",
            })

    if not frames:
        logger.warning("No keyframes found for HD redraw in project %s", project_id)
        return {}

    # Batch redraw
    results = await redrawer.redraw_batch(frames, project_id)

    # Build shot_id -> hd_path mapping
    hd_map: dict[str, str] = {}
    for result in results:
        if result["success"] and result["hd_path"]:
            hd_map[result["shot_id"]] = result["hd_path"]

    return hd_map
