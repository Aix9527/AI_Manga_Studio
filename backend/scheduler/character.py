"""
Scheduler — Character Reference Image Generation

Stage 2: Generate consistent character reference images via ComfyUI.
Optional stage — only runs if characters are defined and not already generated.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from backend.unified_shot import UnifiedShot
from backend.workflow_generator import WorkflowGenerator
from backend.gpu_manager import get_gpu_manager
from backend.config import get_config
from backend.media_cache import get_cache
from backend.generation_log import GenerationLog


@dataclass
class CharacterResult:
    """Result of one character's image generation."""
    name: str
    image_path: str = ""
    success: bool = False


@dataclass
class CharacterStageResult:
    """Aggregated character generation result."""
    characters: List[CharacterResult] = field(default_factory=list)
    total: int = 0
    success: int = 0


class CharacterStage:
    """Generate reference images for each unique character.

    ComfyUI generates, Python assembles prompts and saves results.
    """

    def __init__(self, comfyui_url: str = ""):
        cfg = get_config()
        self.comfyui = get_gpu_manager().get_client("flux")
        self.wf_gen = WorkflowGenerator()

    def generate(
        self,
        shots: List[UnifiedShot],
        output_dir: str,
    ) -> CharacterStageResult:
        """Generate reference images for all unique characters in the shot list.

        Args:
            shots: All shots to scan for characters.
            output_dir: Where to save character reference images.

        Returns:
            CharacterStageResult.
        """
        result = CharacterStageResult()

        # Extract unique characters
        char_set: set[str] = set()
        for shot in shots:
            for c in shot.characters:
                char_set.add(c.strip())

        if not char_set:
            logger.info("CharacterStage: No characters to generate")
            return result

        result.total = len(char_set)
        char_dir = Path(output_dir) / "characters"
        char_dir.mkdir(parents=True, exist_ok=True)

        for name in sorted(char_set):
            cr = self._generate_one(name, str(char_dir))
            result.characters.append(cr)
            if cr.success:
                result.success += 1

        logger.info(f"CharacterStage: {result.success}/{result.total} characters generated")
        return result

    def _generate_one(self, name: str, output_dir: str) -> CharacterResult:
        """Generate a single character reference image, with caching."""
        cr = CharacterResult(name=name)

        # === CACHE CHECK ===
        cache = get_cache()
        cached = cache.get_character(name)
        if cached:
            cr.image_path = cached
            cr.success = True
            logger.info(f"CharacterStage: CACHE HIT '{name}' → {os.path.basename(cached)}")
            return cr

        output_path = os.path.join(output_dir, f"{name}_ref.png")

        # Skip if already exists on disk
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            cr.image_path = output_path
            cr.success = True
            logger.info(f"CharacterStage: '{name}' already exists, skipping")
            return cr

        logger.info(f"CharacterStage: CACHE MISS '{name}' — generating...")
        t0 = time.time()

        try:
            # Build a minimal shot for prompt generation
            shot = UnifiedShot(
                chapter=0, scene=0, shot=0,
                characters=[name],
                background="studio, plain background, character sheet, turnaround",
                camera="medium",
            )

            workflow = self.wf_gen.generate(shot)
            result = self.comfyui.submit_workflow(workflow, wait=True)

            if result:
                images = result.get("images", [])
                if images:
                    cr.image_path = images[0].get("path", output_path)
                else:
                    cr.image_path = output_path
                cr.success = True

                duration = time.time() - t0

                # === GENERATION LOG ===
                gpu = get_gpu_manager().get_gpu_info("flux")
                log = GenerationLog(
                    shot_id=f"char_{name}",
                    category="character",
                    positive_prompt=",".join([name, "character reference sheet", "full body", "studio lighting", "plain background"]) if name else "",
                    negative_prompt="watermark, text, signature",
                    seed=int(workflow.get("seed", -1)),
                    cfg_scale=float(workflow.get("cfg", 7.0)),
                    sampler=str(workflow.get("sampler", "euler_ancestral")),
                    steps=int(workflow.get("steps", 30)),
                    model=str(workflow.get("model", workflow.get("checkpoint", "Flux"))),
                    lora=list(workflow.get("lora", [])),
                    gpu_id=gpu.get("gpu_id", 0) if gpu else 0,
                    gpu_name=gpu.get("name", "") if gpu else "",
                    duration_seconds=duration,
                    output_path=cr.image_path,
                    cache_hit=False,
                )
                log.save()

                logger.info(f"CharacterStage: '{name}' generated → {cr.image_path}")

                # === WRITE CACHE ===
                cache.cache_character(name, cr.image_path)

        except Exception as e:
            logger.error(f"CharacterStage: Failed to generate '{name}': {e}")

        return cr
