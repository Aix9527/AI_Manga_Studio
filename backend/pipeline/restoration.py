"""
AI Manga Studio Pro V2.0 — Layer 7: Image Restoration Pipeline

FLUX output → SUPIR restoration → final image.

Two-tier strategy:
  1. SUPIR (primary)  — denoise, sharpen, detail enhancement, artifact removal
  2. Real-ESRGAN       — fallback when SUPIR is unavailable

SUPIR is invoked via command-line or API; Real-ESRGAN via subprocess.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from backend.model_router import ModelRouter
from backend.resource_manager import ResourceManager


class RestorationError(Exception):
    """Raised when image restoration fails."""


class SUPIRRestorer:
    """SUPIR + Real-ESRGAN image restoration pipeline.

    Usage:
        restorer = SUPIRRestorer()
        output_path = restorer.restore("output/shot_01.png")
    """

    def __init__(self):
        self._router = ModelRouter()
        self._resources = ResourceManager()

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def restore(
        self,
        image_path: str,
        output_dir: Optional[str] = None,
    ) -> str:
        """Restore a single image using SUPIR (fallback: Real-ESRGAN).

        Args:
            image_path: Path to the generated image.
            output_dir: Directory for the restored image. Defaults to same directory.

        Returns:
            Path to the restored image.

        Raises:
            RestorationError: If all restoration methods fail.
        """
        img_path = Path(image_path)
        if not img_path.exists():
            raise RestorationError(f"Image not found: {image_path}")

        if output_dir:
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
        else:
            out_dir = img_path.parent

        model_name, _ = self._router.resolve("super_resolution")

        # Try SUPIR
        if model_name == "supir":
            try:
                result = self._restore_supir(img_path, out_dir)
                logger.info(f"SUPIRRestorer: SUPIR restored → {result}")
                return result
            except Exception as e:
                logger.warning(f"SUPIRRestorer: SUPIR failed ({e}), falling back to Real-ESRGAN")

        # Fallback: Real-ESRGAN
        try:
            result = self._restore_realesrgan(img_path, out_dir)
            logger.info(f"SUPIRRestorer: Real-ESRGAN restored → {result}")
            return result
        except Exception as e:
            raise RestorationError(f"All restoration methods failed: {e}")

    def restore_batch(
        self,
        image_paths: list[str],
        output_dir: Optional[str] = None,
    ) -> list[str]:
        """Restore multiple images sequentially.

        The restoration model (SUPIR) is heavy, so serial execution is enforced
        to stay within the 12 GB VRAM budget.
        """
        model_name, _ = self._router.resolve("super_resolution")
        self._resources.acquire(model_name)
        try:
            results = []
            for img_path in image_paths:
                result = self.restore(img_path, output_dir)
                results.append(result)
            return results
        finally:
            self._resources.release(model_name)

    # ----------------------------------------------------------
    # Internal: SUPIR
    # ----------------------------------------------------------

    @staticmethod
    def _restore_supir(img_path: Path, out_dir: Path) -> str:
        """Run SUPIR via command-line.

        Expected invocation:
            supir --input <img> --output <dir> --scale 4 --denoise 0.5
        """
        output_path = out_dir / f"{img_path.stem}_supir{img_path.suffix}"

        cmd = [
            "supir",
            "--input", str(img_path),
            "--output", str(output_path),
            "--scale", "4",
            "--denoise", "0.5",
            "--tile_size", "512",
            "--tile_overlap", "64",
        ]

        logger.debug(f"SUPIRRestorer: running SUPIR — {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            raise RestorationError(f"SUPIR exited with code {result.returncode}: {result.stderr[:500]}")

        if not output_path.exists():
            raise RestorationError(f"SUPIR output not found: {output_path}")

        return str(output_path)

    # ----------------------------------------------------------
    # Internal: Real-ESRGAN
    # ----------------------------------------------------------

    @staticmethod
    def _restore_realesrgan(img_path: Path, out_dir: Path) -> str:
        """Run Real-ESRGAN via command-line.

        Uses realesrgan-ncnn-vulkan or realesrgan CLI.
        """
        output_path = out_dir / f"{img_path.stem}_esrgan{img_path.suffix}"

        # Try realesrgan-ncnn-vulkan first (fastest)
        cmd_vulkan = [
            "realesrgan-ncnn-vulkan",
            "-i", str(img_path),
            "-o", str(output_path),
            "-s", "4",
            "-n", "realesr-animevideov3",
        ]

        for cmd in [cmd_vulkan, ["realesrgan", "-i", str(img_path), "-o", str(output_path), "--scale", "4"]]:
            try:
                logger.debug(f"SUPIRRestorer: trying Real-ESRGAN — {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                if result.returncode == 0 and output_path.exists():
                    return str(output_path)
            except Exception as e:
                logger.debug(f"SUPIRRestorer: Real-ESRGAN attempt failed: {e}")
                continue

        raise RestorationError(f"Real-ESRGAN failed to produce output at {output_path}")


# Convenience function
def restore_image(image_path: str, output_dir: Optional[str] = None) -> str:
    """Shortcut: restore a single image."""
    return SUPIRRestorer().restore(image_path, output_dir)
