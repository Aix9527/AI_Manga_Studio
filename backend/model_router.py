"""
AI Manga Studio Pro V2.0 — Model Router

Global model dispatch centre. All pipeline stages query the router
rather than hardcoding model choices, enabling runtime overrides
and consistent configuration management.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from loguru import logger

from backend.config import MODEL_ROUTER_CONFIG


class ModelRouter:
    """Singleton model routing table.

    Usage:
        router = ModelRouter()
        model_name, config = router.resolve("character_portrait")
        # or override:
        router.set_override("city_scene", "flux")
    """

    _instance: Optional["ModelRouter"] = None

    def __new__(cls) -> "ModelRouter":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._route_table = dict(MODEL_ROUTER_CONFIG)
            cls._instance._overrides: Dict[str, str] = {}
            cls._instance._workflow_map: Dict[str, str] = {}
            cls._instance._quality_threshold: float = 0.7
            cls._instance._build_workflow_map()
        return cls._instance

    def _build_workflow_map(self) -> None:
        """Map model names to their default ComfyUI workflow filenames."""
        self._workflow_map = {
            "flux": "flux_character.json",
            "flux-schnell": "flux_schnell.json",
            "flux-dev": "flux_dev.json",
            "sdxl": "sdxl_background.json",
            "noobai": "noobai_character.json",
            "kolors": "kolors_character.json",
            "wan2.2": "wan22_i2v.json",
            "hunyuan": "hunyuan_video.json",
            "ltx": "ltx_video.json",
            "supir": "supir_restore.json",
            "codeformer": "codeformer_face.json",
            "pulid": "pulid_flux.json",
            "ipadapter": "ipadapter_faceid.json",
            "instantid": "instantid.json",
            "cosyvoice2": "",           # standalone, no ComfyUI
            "gpt_sovits": "",            # standalone
            "musetalk": "",              # standalone
            "latentsync": "",            # standalone
            "whisper": "",               # standalone
            "ffmpeg": "",                # standalone CPU
        }

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    # ── Quality Threshold & Flux Variant Routing ──────────────

    @property
    def quality_threshold(self) -> float:
        """Threshold above which Flux Dev is selected over Schnell. Default 0.7."""
        return self._quality_threshold

    @quality_threshold.setter
    def quality_threshold(self, value: float) -> None:
        self._quality_threshold = max(0.0, min(1.0, value))

    def route_flux_variant(
        self,
        model_override: str = "",
        quality_score: float = 0.0,
    ) -> str:
        """Route between Flux Schnell (fast preview) and Flux Dev (high quality).

        Rules:
          1. Explicit model override takes precedence (--model flux-dev or --model flux-schnell).
          2. quality_score >= quality_threshold → Flux Dev.
          3. Default → Flux Schnell.
        """
        if model_override in ("flux-dev", "flux_dev"):
            return "flux-dev"
        if model_override in ("flux-schnell", "flux_schnell", "flux"):
            return "flux-schnell"
        if quality_score >= self._quality_threshold:
            return "flux-dev"
        return "flux-schnell"

    # ── Core Resolution ──────────────────────────────────────

    def resolve(
        self,
        task_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """Resolve which model to use for a given task.

        Args:
            task_type: Key from MODEL_ROUTER_CONFIG (e.g. 'character_portrait').
            context: Task-specific hints (e.g. {'art_style': '国漫', 'ethnicity': 'asian'}).
                     May influence routing decisions.

        Returns:
            (model_name, config_dict with 'workflow', 'engine', etc.)
        """
        # Check overrides first
        if task_type in self._overrides:
            model = self._overrides[task_type]
            logger.debug(f"ModelRouter: override {task_type} → {model}")
        else:
            model = self._route_table.get(task_type, "sdxl")
            logger.debug(f"ModelRouter: resolve {task_type} → {model}")

        config = self._build_config(model, task_type, context)
        return model, config

    def set_override(self, task_type: str, model: str) -> None:
        """Override model choice for a specific task type at runtime.

        Args:
            task_type: Task key to override.
            model: Model name to use instead.
        """
        self._overrides[task_type] = model
        logger.info(f"ModelRouter: override set — {task_type} → {model}")

    def clear_overrides(self) -> None:
        """Clear all runtime overrides."""
        self._overrides.clear()
        logger.info("ModelRouter: all overrides cleared")

    def get_workflow(self, model_name: str) -> str:
        """Get ComfyUI workflow filename for a model."""
        return self._workflow_map.get(model_name, "")

    def list_routes(self) -> Dict[str, str]:
        """Get the effective route table (with overrides applied)."""
        effective = dict(self._route_table)
        effective.update(self._overrides)
        return effective

    # ----------------------------------------------------------
    # V3.5: Fine-Grained Routing
    # ----------------------------------------------------------

    def route_character_model(self, character_dna: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Route to optimal character model based on CharacterDNA.

        Uses style_framework and quality_tags from CharacterDNA
        to select between flux/sdxl/noobai/kolors.

        Args:
            character_dna: Dict with keys: style_framework, quality_tags, etc.

        Returns:
            (model_name, config_dict)
        """
        style = character_dna.get("style_framework", "").lower()
        tags = character_dna.get("quality_tags", [])

        # Q版 / 粘土人 → noobai (better for chibi)
        if any(kw in style for kw in ("q版", "卡通", "chibi", "大头", "粘土人")):
            model = "noobai"
        # 写实 / 游戏角色 → flux (photorealistic)
        elif any(kw in style for kw in ("写实", "realistic", "游戏角色", "三视图")):
            model = "flux"
        # 国漫标签 → kolors
        elif any(kw in str(tags).lower() for kw in ("国漫", "水墨", "古风", "东方")):
            model = "kolors"
        else:
            model = "flux"  # default

        config = self._build_config(model, "character_portrait", {"dna": character_dna})
        logger.debug(f"ModelRouter: character model → {model} (style={style})")
        return model, config

    def route_background_model(self, scene_dna: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Route to optimal background/scene model.

        Complex architectural scenes → flux; simple/abstract → sdxl.

        Args:
            scene_dna: Dict with keys: scene_type, environment_tags, complexity.

        Returns:
            (model_name, config_dict)
        """
        scene_type = scene_dna.get("scene_type", "").lower()
        env_tags = scene_dna.get("environment_tags", [])
        complexity = scene_dna.get("complexity", "medium")

        # 建筑 / 室内 → flux (detail-rich)
        if any(kw in scene_type for kw in ("建筑", "宫殿", "城市", "室内", "architecture")):
            model = "flux"
        # 简单野外 → sdxl
        elif any(kw in scene_type for kw in ("自然", "天空", "草地", "森林")):
            model = "sdxl"
        # High complexity → flux
        elif complexity in ("high", "complex"):
            model = "flux"
        else:
            model = "sdxl"

        config = self._build_config(model, "scene_background", {"dna": scene_dna})
        logger.debug(f"ModelRouter: background model → {model} (scene={scene_type})")
        return model, config

    def route_video_model(self, motion_complexity: str) -> Tuple[str, Dict[str, Any]]:
        """Route to optimal video generation model.

        Simple motions → ltx (fast); complex motions → wan2.2 (quality);
        human-centric → hunyuan.

        Args:
            motion_complexity: One of 'simple', 'medium', 'complex'.

        Returns:
            (model_name, config_dict)
        """
        complexity = motion_complexity.lower()

        if complexity == "simple":
            model = "ltx"
        elif complexity == "complex":
            model = "wan2.2"
        else:
            model = "hunyuan"

        config = self._build_config(model, "video_generation", {"complexity": complexity})
        logger.debug(f"ModelRouter: video model → {model} (complexity={complexity})")
        return model, config

    def route_all(
        self,
        character_dna: Optional[Dict[str, Any]] = None,
        scene_dna: Optional[Dict[str, Any]] = None,
        motion_complexity: str = "medium",
    ) -> Dict[str, Tuple[str, Dict[str, Any]]]:
        """Convenience: route all three model types at once.

        Returns dict with keys: character, background, video.
        """
        result: Dict[str, Tuple[str, Dict[str, Any]]] = {}

        if character_dna:
            result["character"] = self.route_character_model(character_dna)
        if scene_dna:
            result["background"] = self.route_background_model(scene_dna)
        result["video"] = self.route_video_model(motion_complexity)

        return result

    # ----------------------------------------------------------
    # Internal
    # ----------------------------------------------------------

    def _build_config(
        self,
        model: str,
        task_type: str,
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build a config dict for the resolved model."""
        workflow = self._workflow_map.get(model, "")

        # Determine engine type
        is_comfyui = workflow != ""
        is_cpu = model in ("ffmpeg", "whisper", "cosyvoice2", "gpt_sovits")
        is_heavy = model in ("flux", "pulid", "wan2.2", "hunyuan")

        return {
            "model": model,
            "workflow": workflow,
            "engine": "comfyui" if is_comfyui else "python",
            "gpu_bound": not is_cpu,
            "heavy": is_heavy,
            "task_type": task_type,
            "context": context or {},
        }

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None


# Convenience function
def resolve_model(task_type: str, context: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
    """Shortcut: resolve a task type without manually creating the router."""
    return ModelRouter().resolve(task_type, context)
