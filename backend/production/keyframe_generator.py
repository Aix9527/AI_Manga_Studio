"""Keyframe image generation module.

Generates first-frame and last-frame images for each shot using ComfyUI.
Supports multiple model backends with automatic fallback:
  1. FLUX (flux-2-klein-4b) - highest quality if available
  2. SDXL (sd_xl_base_1.0) - standard quality, widely available
  3. SD 1.5 (v1-5-pruned) - basic quality, always available
  4. PIL placeholder - text-based fallback when ComfyUI is unavailable

The module also supports:
  - Automatic model detection via ComfyUI API
  - Prompt enhancement with quality boosters
  - Resolution matching to target video dimensions
  - First/last frame generation for interpolation
"""
from __future__ import annotations

import asyncio
import json
import logging
import hashlib
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Quality booster prompt suffixes
QUALITY_BOOSTERS_POS = [
    "masterpiece", "best quality", "highly detailed", "sharp focus",
    "professional photography", "cinematic lighting", "8k uhd",
    "photorealistic", "intricate details",
]
QUALITY_BOOSTERS_NEG = [
    "low quality", "worst quality", "blurry", "distorted",
    "deformed", "bad anatomy", "extra limbs", "watermark",
    "text", "signature", "jpeg artifacts", "pixelated",
    "mosaic", "censored", "duplicate", "split screen",
]

# Portrait dimensions for 9:16 content
TARGET_WIDTH = 832
TARGET_HEIGHT = 1216  # 9:16 portrait

# Model detection order (tried in sequence)
MODEL_PRIORITY = [
    {
        "name": "flux",
        "workflow": "flux_live_action.json",
        "check_models": ["flux-2-klein-4b-fp8.safetensors"],
        "resolution": (512, 896),
    },
    {
        "name": "sdxl",
        "workflow": "sdxl_t2i_keyframe.json",
        "check_models": ["sd_xl_base_1.0.safetensors", "sd_xl_base_1.0_0.9.safetensors"],
        "resolution": (1024, 1024),
    },
    {
        "name": "sd15",
        "workflow": "sdxl_t2i_keyframe.json",
        "check_models": ["v1-5-pruned-emaonly.safetensors", "v1-5-pruned.safetensors"],
        "resolution": (512, 768),
    },
]


class KeyframeGenerator:
    """Generates keyframe images via ComfyUI with automatic model selection."""

    def __init__(self, comfy_base_url: str = "http://127.0.0.1:8188"):
        self.base_url = comfy_base_url
        self._detected_model: str | None = None
        self._detected_workflow: str | None = None

    async def is_available(self) -> bool:
        """Check if ComfyUI is running."""
        try:
            import httpx
            async with httpx.AsyncClient(trust_env=False, timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/system_stats")
                return resp.status_code == 200
        except Exception:
            return False

    async def _list_checkpoints(self) -> list[str]:
        """List available checkpoint models in ComfyUI."""
        try:
            import httpx
            async with httpx.AsyncClient(trust_env=False, timeout=10.0) as client:
                names: list[str] = []
                for endpoint, key in (("CheckpointLoaderSimple", "ckpt_name"),
                                      ("UNETLoader", "unet_name")):
                    resp = await client.get(f"{self.base_url}/object_info/{endpoint}")
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    info = data.get(endpoint, {})
                    inputs = info.get("input", {})
                    values = inputs.get("required", {}).get(key, [[]])[0]
                    if isinstance(values, list):
                        names.extend(str(v) for v in values)
                return sorted(set(names))
        except Exception as exc:
            logger.debug("Failed to list checkpoints: %s", exc)
            return []

    async def detect_best_model(self) -> str | None:
        """Detect the best available model for keyframe generation."""
        if self._detected_model is not None:
            return self._detected_model

        checkpoints = await self._list_checkpoints()
        if not checkpoints:
            logger.warning("No checkpoints found in ComfyUI")
            return None

        logger.info("Available checkpoints: %s", checkpoints[:10])

        for candidate in MODEL_PRIORITY:
            for expected in candidate["check_models"]:
                # Match by substring (handles versioned filenames)
                for ckpt in checkpoints:
                    if expected.lower() in ckpt.lower():
                        self._detected_model = ckpt
                        self._detected_workflow = candidate["workflow"]
                        logger.info("Detected best model: %s (workflow: %s)",
                                    ckpt, candidate["workflow"])
                        return ckpt

        # Use first available checkpoint as fallback
        if checkpoints:
            self._detected_model = checkpoints[0]
            self._detected_workflow = "sdxl_t2i_keyframe.json"
            logger.info("Using fallback checkpoint: %s", checkpoints[0])
            return checkpoints[0]

        return None

    def _enhance_prompt(self, prompt: str, shot_data: dict) -> str:
        """Enhance prompt with quality boosters and scene-specific descriptors."""
        parts = [prompt]

        # Add scene description if available
        desc = shot_data.get("description", "")
        if desc:
            parts.append(desc)

        # Add camera angle if available
        camera = shot_data.get("camera", "")
        if camera:
            parts.append(camera)

        # Add quality boosters
        parts.extend(QUALITY_BOOSTERS_POS[:5])

        return ", ".join(p for p in parts if p)

    def _build_negative_prompt(self, existing_neg: str = "") -> str:
        """Build comprehensive negative prompt to prevent artifacts."""
        parts = [p for p in [existing_neg] if p]
        parts.extend(QUALITY_BOOSTERS_NEG)
        # GPT Round-1: Anatomy Guard —— 手/脸/肢体/武器畸形负向限制
        try:
            from backend.video.action_prompts import ANATOMY_GUARD_NEGATIVES
            parts.extend(a for a in ANATOMY_GUARD_NEGATIVES if a not in parts)
        except Exception:
            pass
        return ", ".join(p for p in parts if p)

    async def generate_keyframe(
        self,
        shot_data: dict,
        output_path: Path,
        frame_type: str = "first",
    ) -> bool:
        """Generate a keyframe image for a shot.

        Args:
            shot_data: Shot dictionary with description, prompt, etc.
            output_path: Where to save the generated image.
            frame_type: "first" or "last" frame for interpolation.

        Returns:
            True if generation succeeded, False otherwise.
        """
        shot_id = shot_data.get("id", "unknown")

        if not await self.is_available():
            logger.warning("ComfyUI not available for keyframe generation: %s", shot_id)
            return self._generate_placeholder(shot_data, output_path, frame_type)

        model = await self.detect_best_model()
        if model is None:
            logger.warning("No suitable model found for keyframe generation: %s", shot_id)
            return self._generate_placeholder(shot_data, output_path, frame_type)

        # Load workflow template
        workflow_path = Path("backend/production/workflows") / (self._detected_workflow or "sdxl_t2i_keyframe.json")
        if not workflow_path.exists():
            logger.error("Workflow file not found: %s", workflow_path)
            return self._generate_placeholder(shot_data, output_path, frame_type)

        with open(workflow_path, "r", encoding="utf-8") as f:
            template = json.load(f)
        workflow = dict(template["workflow"])
        bindings = template["bindings"]

        # Prepare prompts
        base_prompt = shot_data.get("positive_prompt", "")
        if not base_prompt:
            base_prompt = (shot_data.get("prompt", "")
                           or shot_data.get("description", "cinematic scene"))
        enhanced_prompt = self._enhance_prompt(base_prompt, shot_data)
        negative_prompt = self._build_negative_prompt(shot_data.get("negative_prompt", ""))

        # For last frame, modify prompt slightly to show end state
        if frame_type == "last":
            enhanced_prompt = f"{enhanced_prompt}, end of scene, settled composition"

        # Get shot seed or generate one
        # GPT Round-1: seed 纳入 shot_id + frame_type + prompt 内容，
        # 避免"固定 seed + 高度相似 prompt"导致所有首帧雷同
        seed = shot_data.get("seed", 0)
        if seed == 0:
            seed_str = f"{shot_id}|{frame_type}|{enhanced_prompt}"
            seed = abs(hash(seed_str)) % 1000000

        # Fill in workflow parameters
        if "prompt" in bindings:
            workflow[bindings["prompt"][0]]["inputs"][bindings["prompt"][1]] = enhanced_prompt
        if "negative_prompt" in bindings:
            workflow[bindings["negative_prompt"][0]]["inputs"][bindings["negative_prompt"][1]] = negative_prompt
        if "seed" in bindings:
            workflow[bindings["seed"][0]]["inputs"][bindings["seed"][1]] = seed
        if "checkpoint" in bindings:
            workflow[bindings["checkpoint"][0]]["inputs"][bindings["checkpoint"][1]] = model
        if "filename_prefix" in bindings:
            workflow[bindings["filename_prefix"][0]]["inputs"][bindings["filename_prefix"][1]] = \
                f"novel_video/{output_path.stem}"

        # Set resolution based on model type
        # Shot-level resolution override wins; otherwise use model defaults
        try:
            w = int(shot_data.get("width") or 0) or None
            h = int(shot_data.get("height") or 0) or None
        except Exception:  # noqa: BLE001
            w = h = None
        if w is None or h is None:
            if self._detected_workflow and "flux" in self._detected_workflow:
                w, h = 512, 896
            else:
                w, h = 832, 1216
        if "width" in bindings:
            w_binding = bindings["width"]
            if isinstance(w_binding[0], list):
                for wb in w_binding:
                    workflow[wb[0]]["inputs"][wb[1]] = w
            else:
                workflow[w_binding[0]]["inputs"][w_binding[1]] = w
        if "height" in bindings:
            h_binding = bindings["height"]
            if isinstance(h_binding[0], list):
                for hb in h_binding:
                    workflow[hb[0]]["inputs"][hb[1]] = h
            else:
                workflow[h_binding[0]]["inputs"][h_binding[1]] = h

        logger.info("Generating keyframe for %s (%s frame) using %s",
                    shot_id, frame_type, model)

        try:
            import httpx
            import time

            # Submit workflow
            async with httpx.AsyncClient(trust_env=False, timeout=30) as client:
                submit_resp = await client.post(
                    f"{self.base_url}/prompt",
                    json={"prompt": workflow},
                )
                submit_data = submit_resp.json()

            if submit_resp.status_code >= 400:
                logger.error("ComfyUI rejected workflow: %s", str(submit_data)[:500])
                return self._generate_placeholder(shot_data, output_path, frame_type)

            prompt_id = submit_data.get("prompt_id", "")
            if not prompt_id:
                logger.error("No prompt_id from ComfyUI")
                return self._generate_placeholder(shot_data, output_path, frame_type)

            # Wait for completion (up to 5 minutes)
            start = time.monotonic()
            timeout = 300
            while time.monotonic() - start < timeout:
                async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                    hist_resp = await client.get(f"{self.base_url}/history/{prompt_id}")

                data = hist_resp.json()
                entry = data.get(prompt_id)
                if entry is not None:
                    outputs = entry.get("outputs", {})
                    status = entry.get("status", {})
                    if outputs:
                        # Download the first image artifact
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
                                            logger.info("Keyframe saved: %s (%d KB)",
                                                        output_path.name,
                                                        len(dl_resp.content) // 1024)
                                            # GPT Round-1: 首帧雷同检测（与同集其他镜头首帧 pHash 距离）
                                            if frame_type == "first" and output_path.suffix.lower() in (".png", ".jpg", ".jpeg"):
                                                if self._is_duplicate_first_frame(output_path):
                                                    logger.warning(
                                                        "Keyframe %s 与同集其他镜头首帧过于相似，判为重样",
                                                        output_path.name,
                                                    )
                                                    return False
                                            return True
                        logger.warning("ComfyUI completed but no image artifact")
                        return self._generate_placeholder(shot_data, output_path, frame_type)

                    if status.get("status_str") == "error":
                        messages = status.get("messages", [])
                        for msg in reversed(messages):
                            if isinstance(msg, list) and len(msg) == 2 and msg[0] == "execution_error":
                                err = msg[1]
                                logger.error("ComfyUI error: %s (node: %s)",
                                             err.get("exception_message", "Unknown"),
                                             err.get("node_type", "?"))
                                return self._generate_placeholder(shot_data, output_path, frame_type)

                    if status.get("completed"):
                        logger.warning("ComfyUI completed but no outputs")
                        return self._generate_placeholder(shot_data, output_path, frame_type)

                await asyncio.sleep(2)

            logger.warning("ComfyUI keyframe generation timed out after %ds", timeout)
            return self._generate_placeholder(shot_data, output_path, frame_type)

        except Exception as exc:
            logger.error("Keyframe generation failed: %s", exc, exc_info=True)
            return self._generate_placeholder(shot_data, output_path, frame_type)

    @staticmethod
    def _perceptual_hash(image_path: Path, hash_size: int = 8) -> str:
        """Gradient-based dHash (64-bit hex). Dependency-light duplicate check."""
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                gray = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
            pixels = list(gray.getdata())
            bits: list[str] = []
            for row in range(hash_size):
                for col in range(hash_size):
                    left = pixels[row * (hash_size + 1) + col]
                    right = pixels[row * (hash_size + 1) + col + 1]
                    bits.append("1" if left > right else "0")
            return "".join(bits)
        except Exception:
            return ""

    @staticmethod
    def _hamming_distance(a: str, b: str) -> int:
        return sum(1 for x, y in zip(a, b) if x != y)

    def _is_duplicate_first_frame(self, output_path: Path, threshold: int = 4) -> bool:
        """Compare the generated first frame with sibling shots' first frames.

        Scans ``images/*/*_start.png`` under the episode images root. Returns
        True when any sibling first frame is perceptually too close.
        """
        output_path = Path(output_path)
        new_hash = self._perceptual_hash(output_path)
        if not new_hash:
            return False
        shot_dir = output_path.parent
        images_root = shot_dir.parent  # e.g. .../episode/images/
        if not images_root.is_dir():
            return False
        siblings = [
            p for p in images_root.glob("*/*_start.png")
            if p.resolve() != output_path.resolve()
        ]
        for sibling in siblings:
            try:
                h = self._perceptual_hash(sibling)
                if h and self._hamming_distance(new_hash, h) < threshold:
                    return True
            except Exception:
                continue
        return False

    def _generate_placeholder(
        self,
        shot_data: dict,
        output_path: Path,
        frame_type: str,
    ) -> bool:
        """Generate a high-quality placeholder image using PIL when ComfyUI is unavailable.

        Creates a gradient background with the shot description rendered as text,
        ensuring the output file exists even when AI generation is not possible.
        """
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageFilter
            import random

            # Create a cinematic gradient background
            width, height = 832, 1216
            img = Image.new("RGB", (width, height))

            # Generate a seed-based gradient
            seed = shot_data.get("seed", 42)
            random.seed(seed + (1 if frame_type == "last" else 0))

            # Pick a color palette based on scene description
            desc = (shot_data.get("description", "") + shot_data.get("narration", "")).lower()
            if any(w in desc for w in ["dark", "night", "shadow", "dark"]):
                base_color = (15, 20, 40)
                accent_color = (60, 80, 120)
            elif any(w in desc for w in ["warm", "sun", "gold", "fire"]):
                base_color = (40, 25, 10)
                accent_color = (120, 80, 30)
            elif any(w in desc for w in ["green", "forest", "nature", "garden"]):
                base_color = (10, 30, 15)
                accent_color = (30, 80, 40)
            elif any(w in desc for w in ["lab", "tech", "science", "futuristic"]):
                base_color = (10, 15, 30)
                accent_color = (40, 60, 100)
            else:
                base_color = (25, 20, 35)
                accent_color = (70, 60, 90)

            # Draw gradient
            for y in range(height):
                ratio = y / height
                r = int(base_color[0] + (accent_color[0] - base_color[0]) * ratio)
                g = int(base_color[1] + (accent_color[1] - base_color[1]) * ratio)
                b = int(base_color[2] + (accent_color[2] - base_color[2]) * ratio)
                for x in range(width):
                    noise = random.randint(-8, 8)
                    img.putpixel((x, y), (
                        max(0, min(255, r + noise)),
                        max(0, min(255, g + noise)),
                        max(0, min(255, b + noise)),
                    ))

            # Add subtle vignette
            vignette = Image.new("L", (width, height), 0)
            draw_v = ImageDraw.Draw(vignette)
            for i in range(100):
                alpha = int(255 * (1 - i / 100) * 0.3)
                draw_v.rectangle(
                    [i, i, width - i, height - i],
                    fill=alpha,
                )
            img = Image.composite(img, Image.new("RGB", (width, height), (0, 0, 0)), vignette)

            # Add text overlay
            draw = ImageDraw.Draw(img)
            shot_id = shot_data.get("id", "unknown")
            description = shot_data.get("description", "")
            camera = shot_data.get("camera", "")
            narration = shot_data.get("narration", "")

            # Try to load a font
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/segoeui.ttf",
            ]
            font_large = None
            font_small = None
            for fp in font_paths:
                try:
                    font_large = ImageFont.truetype(fp, 28)
                    font_small = ImageFont.truetype(fp, 18)
                    break
                except Exception:
                    continue
            if font_large is None:
                font_large = ImageFont.load_default()
                font_small = font_large

            # Draw shot ID
            draw.text((20, 30), f"[{shot_id}] {frame_type.upper()} FRAME",
                      fill=(255, 255, 255), font=font_large)

            # Draw description (wrapped)
            y_offset = 100
            if description:
                words = description.split()
                lines = []
                current_line = []
                for word in words:
                    current_line.append(word)
                    line = " ".join(current_line)
                    if font_small.getlength(line) > width - 40:
                        current_line.pop()
                        lines.append(" ".join(current_line))
                        current_line = [word]
                if current_line:
                    lines.append(" ".join(current_line))
                for line in lines[:15]:
                    draw.text((20, y_offset), line, fill=(220, 220, 220), font=font_small)
                    y_offset += 24

            # Draw camera info
            if camera:
                y_offset += 20
                draw.text((20, y_offset), f"Camera: {camera}",
                          fill=(180, 180, 255), font=font_small)

            # Draw narration
            if narration:
                y_offset += 30
                words = narration.split()
                lines = []
                current_line = []
                for word in words:
                    current_line.append(word)
                    line = " ".join(current_line)
                    if font_small.getlength(line) > width - 40:
                        current_line.pop()
                        lines.append(" ".join(current_line))
                        current_line = [word]
                if current_line:
                    lines.append(" ".join(current_line))
                for line in lines[:8]:
                    draw.text((20, y_offset), line, fill=(200, 200, 200), font=font_small)
                    y_offset += 22

            # Apply slight blur for cinematic look
            img = img.filter(ImageFilter.GaussianBlur(radius=0.5))

            output_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(output_path, format="PNG", quality=95)
            logger.info("Placeholder keyframe saved: %s (%d KB)",
                        output_path.name, output_path.stat().st_size // 1024)
            return True

        except Exception as exc:
            logger.error("Placeholder generation failed: %s", exc)
            # Last resort: create minimal file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            # Create a 1x1 pixel PNG
            from PIL import Image as PILImage
            PILImage.new("RGB", (1, 1), (20, 20, 30)).save(output_path, format="PNG")
            return True
