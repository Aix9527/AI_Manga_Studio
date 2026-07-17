"""
AI Manga Studio Pro V2.0 — Layer 4: Background Model Router

Routes background generation requests to the optimal model based on scene type:

    city / urban / 都市       → SDXL   (fast, rich urban training data)
    ancient / 古风 / 仙侠     → FLUX   (best ancient architecture detail)
    architecture / 建筑       → FLUX
    landscape / 风景 / 自然   → SDXL
    scifi / 科幻             → FLUX

Each route points to a dedicated ComfyUI workflow template (sdxl_bg.json / flux_bg.json).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from loguru import logger

from backend.config import PIPELINE_CONFIG
from backend.model_router import ModelRouter


# ---------------------------------------------------------------------------
# Scene type constants
# ---------------------------------------------------------------------------

CITY_KEYWORDS = {"city", "urban", "都市", "城市", "城镇", "街道", "城区", "street"}
ANCIENT_KEYWORDS = {"ancient", "古风", "仙侠", "古装", "古典", "寺庙", "宫殿", "武侠"}
ARCHITECTURE_KEYWORDS = {"architecture", "建筑", "building", "structure"}
LANDSCAPE_KEYWORDS = {"landscape", "风景", "自然", "natural", "山水", "田园", "森林", "ocean", "mountain"}
SCIFI_KEYWORDS = {"scifi", "sci-fi", "科幻", "未来", "赛博朋克", "cyberpunk", "future"}


class BackgroundRouter:
    """Route background scene descriptions to the optimal image model.

    Usage:
        router = BackgroundRouter()
        model_name, workflow = router.route("ancient temple gate")
        # → ("flux", "flux_bg.json")
    """

    def __init__(
        self,
        workflow_dir: Optional[str] = None,
    ):
        """Args:
            workflow_dir: Override path to ComfyUI workflow JSONs.
                          Defaults to <project>/comfyui_workflows/.
        """
        self._router = ModelRouter()
        if workflow_dir:
            self._workflow_dir = Path(workflow_dir)
        else:
            self._workflow_dir = Path(__file__).resolve().parent.parent.parent / "comfyui_workflows"

        # Workflow template mapping
        self._workflows: Dict[str, str] = {
            "sdxl": "sdxl_bg.json",
            "flux": "flux_bg.json",
        }

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def route(self, scene_description: str) -> Tuple[str, str]:
        """Determine best model for a scene description.

        Args:
            scene_description: Natural language (Chinese or English) scene description.

        Returns:
            (model_name, workflow_filename)
        """
        scene_type = self._classify_scene(scene_description)
        logger.debug(f"BackgroundRouter: scene='{scene_description[:40]}...' → type={scene_type}")

        task_map = {
            "city": "city_scene",
            "ancient": "ancient_architecture",
            "architecture": "ancient_architecture",
            "landscape": "landscape_scene",
            "scifi": "scifi_scene",
        }
        task_type = task_map.get(scene_type, "landscape_scene")
        model_name, _ = self._router.resolve(task_type)
        workflow = self._workflows.get(model_name, self._workflows["sdxl"])

        return model_name, workflow

    def route_with_config(self, scene_description: str) -> Dict[str, Any]:
        """Same as route() but returns a full config dict for the pipeline."""
        model_name, workflow = self.route(scene_description)
        return {
            "model": model_name,
            "workflow": str(self._workflow_dir / workflow),
            "scene_type": self._classify_scene(scene_description),
        }

    def load_workflow_template(self, workflow_filename: str) -> Dict[str, Any]:
        """Load and parse a ComfyUI workflow JSON template.

        Args:
            workflow_filename: Base filename in comfyui_workflows/ (e.g. 'flux_bg.json').

        Returns:
            Parsed workflow dict.
        """
        path = self._workflow_dir / workflow_filename
        if not path.exists():
            logger.warning(f"BackgroundRouter: workflow not found: {path}, using empty template")
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ----------------------------------------------------------
    # Internal
    # ----------------------------------------------------------

    @staticmethod
    def _classify_scene(description: str) -> str:
        """Classify a scene description into one of: city|ancient|architecture|landscape|scifi."""
        desc_lower = description.lower()

        # Priority: ancient before architecture (ancient architecture is still ancient)
        for kw in ANCIENT_KEYWORDS:
            if kw in desc_lower:
                return "ancient"

        for kw in SCIFI_KEYWORDS:
            if kw in desc_lower:
                return "scifi"

        for kw in CITY_KEYWORDS:
            if kw in desc_lower:
                return "city"

        for kw in ARCHITECTURE_KEYWORDS:
            if kw in desc_lower:
                return "architecture"

        for kw in LANDSCAPE_KEYWORDS:
            if kw in desc_lower:
                return "landscape"

        # Default: landscape (safe general-purpose)
        return "landscape"


# Convenience function
def route_background(scene_description: str) -> Dict[str, Any]:
    """Shortcut: route a background scene and return config."""
    return BackgroundRouter().route_with_config(scene_description)
