"""
Scheduler — Scene Background Generation

Stage 3: Generate scene background images via ComfyUI.
Optional stage — generates empty background plates for composition.
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
class SceneBgResult:
    """Result of one scene background generation."""
    name: str
    image_path: str = ""
    success: bool = False


@dataclass
class SceneStageResult:
    """Aggregated scene generation result."""
    scenes: List[SceneBgResult] = field(default_factory=list)
    total: int = 0
    success: int = 0


class SceneStage:
    """Generate background images for each unique scene.

    ComfyUI generates, Python handles everything else.

    After generation, each shot's background_image_path field
    is updated so downstream stages (ImageStage, RenderStage)
    can use the scene background for composition.
    """

    def __init__(self, comfyui_url: str = ""):
        cfg = get_config()
        self.comfyui = get_gpu_manager().get_client("flux")
        self.wf_gen = WorkflowGenerator()

    def generate(
        self,
        shots: List[UnifiedShot],
        output_dir: str,
    ) -> SceneStageResult:
        """Generate backgrounds for all unique scenes in the shot list.

        After generation, each matching shot gets its
        background_image_path set to the generated background.

        Args:
            shots: All shots to scan for scenes.
            output_dir: Where to save background images.

        Returns:
            SceneStageResult.
        """
        result = SceneStageResult()

        # Extract unique scenes
        scene_set: set[str] = set()
        for shot in shots:
            if shot.background:
                scene_set.add(shot.background.strip())

        if not scene_set:
            logger.info("SceneStage: No scenes to generate")
            return result

        result.total = len(scene_set)
        bg_dir = Path(output_dir) / "backgrounds"
        bg_dir.mkdir(parents=True, exist_ok=True)

        # Map scene name → generated image path
        scene_bg_map: Dict[str, str] = {}

        for name in sorted(scene_set):
            sr = self._generate_one(name, str(bg_dir))
            result.scenes.append(sr)
            if sr.success:
                result.success += 1
                scene_bg_map[name] = sr.image_path

        # === Inject background paths into matching shots ===
        injected = 0
        for shot in shots:
            bg_name = (shot.background or "").strip()
            if bg_name in scene_bg_map:
                shot.background_image_path = scene_bg_map[bg_name]
                if shot.json_path:
                    shot.to_json_file(shot.json_path)
                injected += 1

        if injected > 0:
            logger.info(
                f"SceneStage: Injected background paths into "
                f"{injected} shots ({len(scene_bg_map)} unique scenes)"
            )

        logger.info(f"SceneStage: {result.success}/{result.total} backgrounds generated")
        return result

    def _generate_one(self, name: str, output_dir: str) -> SceneBgResult:
        """Generate a single background image, with caching."""
        sr = SceneBgResult(name=name)

        # === CACHE CHECK ===
        cache = get_cache()
        cached = cache.get_scene(name)
        if cached:
            sr.image_path = cached
            sr.success = True
            logger.info(f"SceneStage: CACHE HIT '{name}' → {os.path.basename(cached)}")
            return sr

        safe_name = name.replace(" ", "_").replace("/", "_")
        output_path = os.path.join(output_dir, f"{safe_name}_bg.png")

        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            sr.image_path = output_path
            sr.success = True
            return sr

        logger.info(f"SceneStage: CACHE MISS '{name}' — generating...")
        t0 = time.time()

        try:
            shot = UnifiedShot(
                chapter=0, scene=0, shot=0,
                background=name,
                camera="wide",
                weather="clear",
                time_of_day="noon",
            )

            workflow = self.wf_gen.generate(shot)
            result = self.comfyui.submit_workflow(workflow, wait=True)

            if result:
                images = result.get("images", [])
                sr.image_path = images[0].get("path", output_path) if images else output_path
                sr.success = True

                duration = time.time() - t0

                # === GENERATION LOG ===
                gpu = get_gpu_manager().get_gpu_info("flux")
                log = GenerationLog(
                    shot_id=f"scene_{name}",
                    category="scene",
                    positive_prompt=getattr(shot, "positive_prompt", "") or name,
                    negative_prompt="people, characters, text, watermark",
                    seed=int(workflow.get("seed", -1)),
                    cfg_scale=float(workflow.get("cfg", 7.0)),
                    sampler=str(workflow.get("sampler", "euler_ancestral")),
                    steps=int(workflow.get("steps", 30)),
                    model=str(workflow.get("model", workflow.get("checkpoint", "Flux"))),
                    lora=list(workflow.get("lora", [])),
                    gpu_id=gpu.get("gpu_id", 0) if gpu else 0,
                    gpu_name=gpu.get("name", "") if gpu else "",
                    duration_seconds=duration,
                    output_path=sr.image_path,
                    cache_hit=False,
                )
                log.save()

                logger.info(f"SceneStage: '{name}' generated")

                # === WRITE CACHE ===
                cache.cache_scene(name, sr.image_path)

        except Exception as e:
            logger.error(f"SceneStage: Failed to generate '{name}': {e}")

        return sr
