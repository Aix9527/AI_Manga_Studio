"""
Generation Planning — Prompt compilation and multi-provider execution (Part 32)

Provides:
- PromptCompiler: Compiles shot specs into provider-optimized prompts
- GenerationPlan: Complete task graph for a generation run
- ProviderRouter: Selects optimal provider for each generation task
- ParameterOptimizer: Tunes generation parameters per shot
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GenerationTask(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class ProviderPreference(str, Enum):
    QUALITY = "quality"
    SPEED = "speed"
    COST = "cost"
    LOCAL = "local"
    CLOUD = "cloud"


@dataclass
class PromptTemplate:
    """Template for a specific provider's prompt format."""
    provider_name: str
    template_str: str  # e.g., "masterpiece, best quality, {subject}, {style}"
    negative_default: str = "low quality, blurry, deformed, watermark"
    prefix: str = ""
    suffix: str = ""
    max_length: int = 500


@dataclass
class GenerationTaskConfig:
    """Single generation task specification."""
    task_id: str = ""
    task_type: GenerationTask = GenerationTask.IMAGE
    shot_number: int = 0
    character_ids: list[str] = field(default_factory=list)

    # Prompt
    prompt: str = ""
    negative_prompt: str = ""

    # Parameters
    width: int = 1024
    height: int = 1024
    seed: int = 0
    steps: int = 30
    cfg_scale: float = 7.0

    # Video-specific
    fps: int = 24
    duration_frames: int = 72
    motion_bucket_id: int = 127

    # Provider routing
    preferred_provider: str = ""
    fallback_providers: list[str] = field(default_factory=list)

    # Dependency
    depends_on: list[str] = field(default_factory=list)  # task IDs this depends on


@dataclass
class GenerationPlan:
    """
    Complete generation plan — a graph of GenerationTaskConfig nodes.

    Compiled by PromptCompiler, executed by the WorkflowEngine.
    """
    plan_id: str = ""
    project_id: str = ""
    tasks: list[GenerationTaskConfig] = field(default_factory=list)
    total_tasks: int = 0
    estimated_cost: float = 0.0
    estimated_time_seconds: float = 0.0

    def add_task(self, task: GenerationTaskConfig) -> None:
        self.tasks.append(task)
        self.total_tasks += 1

    def get_task_by_shot(self, shot_number: int) -> GenerationTaskConfig | None:
        for t in self.tasks:
            if t.shot_number == shot_number:
                return t
        return None


# ── Prompt Compiler ───────────────────────────────────────────────────

class PromptCompiler:
    """
    Compiles shot specifications into provider-optimized prompts.

    Supports template-based compilation for:
    - ComfyUI / Flux (tag-based: "masterpiece, best quality, ...")
    - OpenAI DALL-E (natural language)
    - Midjourney-style (parameters: --ar 16:9 --style raw)
    - Stable Diffusion WebUI (weighted prompts)
    """

    def __init__(self) -> None:
        self._templates: dict[str, PromptTemplate] = {
            "comfyui": PromptTemplate(
                provider_name="comfyui",
                template_str="masterpiece, best quality, {subject}, {style}, {lighting}, {composition}",
                negative_default="lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry",
            ),
            "openai": PromptTemplate(
                provider_name="openai",
                template_str="{description}. {style}. The scene is lit with {lighting}. Camera: {camera}.",
            ),
            "flux": PromptTemplate(
                provider_name="flux",
                template_str="cinematic, highly detailed, {subject}, {style}, {lighting} lighting, {composition}",
            ),
        }

    def add_template(self, name: str, template: PromptTemplate) -> None:
        self._templates[name] = template

    def compile(
        self,
        shot: dict[str, Any],
        provider: str = "comfyui",
        character_dnas: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """
        Compile a shot into (prompt, negative_prompt) for a given provider.

        Args:
            shot: Shot specification dict
            provider: Target provider name
            character_dnas: Optional character DNA dicts for character-specific tags

        Returns:
            (prompt, negative_prompt) tuple
        """
        template = self._templates.get(provider, self._templates["comfyui"])

        # Build substitutions
        substitutions = {
            "subject": shot.get("description", ""),
            "style": shot.get("style", "anime"),
            "lighting": shot.get("lighting", "natural"),
            "composition": shot.get("composition_rule", "rule of thirds"),
            "camera": shot.get("camera_angle", "eye level"),
            "description": shot.get("description", ""),
        }

        # Inject character DNA tags
        if character_dnas:
            character_tags = []
            for char_id in shot.get("characters_in_frame", []):
                if char_id in character_dnas:
                    character_tags.append(character_dnas[char_id].get_prompt_tags())
            if character_tags:
                substitutions["subject"] += " with " + ", ".join(character_tags)

        # Fill template
        try:
            prompt = template.template_str.format(**substitutions)
        except KeyError:
            prompt = template.template_str.replace("{subject}", shot.get("description", ""))

        if template.prefix:
            prompt = f"{template.prefix} {prompt}"
        if template.suffix:
            prompt = f"{prompt} {template.suffix}"

        # Truncate if needed
        if len(prompt) > template.max_length:
            prompt = prompt[:template.max_length - 3] + "..."

        negative = template.negative_default

        return prompt, negative


# ── Provider Router ───────────────────────────────────────────────────

class ProviderRouter:
    """
    Routes generation tasks to optimal providers.

    Criteria:
    - Task type (image/video/audio)
    - Quality requirements
    - Latency constraints
    - Cost limits
    - Provider availability
    """

    def __init__(self) -> None:
        self._provider_capabilities: dict[str, dict[str, Any]] = {}

    def register_provider(
        self,
        name: str,
        task_types: list[str],
        quality_score: float = 0.8,
        avg_latency_ms: int = 5000,
        cost_credits: float = 1.0,
    ) -> None:
        self._provider_capabilities[name] = {
            "task_types": task_types,
            "quality_score": quality_score,
            "avg_latency_ms": avg_latency_ms,
            "cost_credits": cost_credits,
        }

    def select(
        self,
        task_type: GenerationTask,
        preference: ProviderPreference = ProviderPreference.QUALITY,
        max_cost: float = 10.0,
    ) -> str:
        """Select the best provider for a task type based on preference."""
        candidates = {
            name: info for name, info in self._provider_capabilities.items()
            if task_type.value in info.get("task_types", [])
            and info.get("cost_credits", 0) <= max_cost
        }

        if not candidates:
            return "comfyui"  # Default fallback

        if preference == ProviderPreference.QUALITY:
            return max(candidates.items(), key=lambda x: x[1]["quality_score"])[0]
        elif preference == ProviderPreference.SPEED:
            return min(candidates.items(), key=lambda x: x[1]["avg_latency_ms"])[0]
        elif preference == ProviderPreference.COST:
            return min(candidates.items(), key=lambda x: x[1]["cost_credits"])[0]
        else:
            return list(candidates.keys())[0]


# ── Parameter Optimizer ───────────────────────────────────────────────

class ParameterOptimizer:
    """
    Optimizes generation parameters per shot context.

    Adjusts:
    - Steps/CGF based on complexity
    - Resolution based on shot type
    - Seed strategy for consistency
    """

    @staticmethod
    def optimize_for_shot(shot: dict[str, Any], task_type: GenerationTask) -> dict[str, Any]:
        """Return optimized parameters for a shot."""
        params: dict[str, Any] = {
            "steps": 30,
            "cfg_scale": 7.0,
        }

        shot_type = shot.get("shot_type", "medium")

        # Fewer steps for simple shots
        if shot_type in ("wide", "extreme_wide"):
            params["steps"] = 20
        elif shot_type in ("close_up", "extreme_close"):
            params["steps"] = 35  # More detail needed

        # Face detail boost for close-ups
        if shot_type in ("close_up", "extreme_close"):
            params["cfg_scale"] = 7.5

        return params
