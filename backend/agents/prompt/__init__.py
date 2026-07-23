"""
Prompt Engineering Agent (Part 9)

Constructs optimized generation prompts for image and video models.
Transforms storyboard shots, character profiles, and scene descriptions
into model-specific prompts with proper style tags, negative prompts,
and parameter tuning.

Supports multiple prompt formats: ComfyUI workflow JSON, Wan video prompt,
Flux/SDXL T2I prompt, etc.
"""

from __future__ import annotations

from typing import Any

from backend.agents.base_agent import (
    BaseAgent,
    AgentContext,
    AgentResult,
    AgentStatus,
)


class PromptAgent(BaseAgent[AgentResult]):
    """
    Prompt construction agent for image and video generation.

    Input: Storyboard shots + character profiles + scene descriptions
    Output: Model-optimized prompts with style tags and parameters

    Capabilities:
    - Image prompt generation (Flux, SDXL, ComfyUI workflow)
    - Video prompt generation (Wan, AnimateDiff)
    - Style tag injection
    - Negative prompt construction
    - Parameter tuning (steps, cfg, resolution)
    """

    def __init__(
        self,
        agent_id: str = "prompt_agent",
        agent_type: str = "prompt",
    ) -> None:
        super().__init__(agent_id=agent_id, agent_type=agent_type)
        self.capabilities = [
            "image_prompt_generation",
            "video_prompt_generation",
            "style_tag_injection",
            "negative_prompt_construction",
            "comfyui_workflow_generation",
        ]

    async def _execute_impl(
        self, context: AgentContext, **kwargs: Any
    ) -> AgentResult:
        """
        Generate optimized prompts for all shots.

        Args:
            storyboard: Storyboard with shots
            characters: Character profiles
            scenes: Enriched scene descriptions
            style: Overall art style
            output_format: "flux", "sdxl", "comfyui", "wan"

        Returns:
            AgentResult with prompts for each shot
        """
        storyboard = kwargs.get("storyboard", {})
        shots = storyboard.get("shots", [])
        characters = kwargs.get("characters", [])
        scenes = kwargs.get("scenes", [])
        style = kwargs.get("style", "anime_manga")
        output_format = kwargs.get("output_format", "comfyui")

        generated_prompts = []
        for i, shot in enumerate(shots[:50]):  # Limit for MVP
            prompt_data = self._generate_shot_prompt(
                shot=shot,
                shot_index=i,
                characters=characters,
                scenes=scenes,
                style=style,
                output_format=output_format,
            )
            generated_prompts.append(prompt_data)

        return AgentResult(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            status=AgentStatus.COMPLETED,
            output={
                "prompts": generated_prompts,
                "prompt_count": len(generated_prompts),
                "style": style,
                "output_format": output_format,
            },
        )

    @classmethod
    def input_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "storyboard": {"type": "object"},
                "characters": {"type": "array"},
                "scenes": {"type": "array"},
                "style": {"type": "string"},
                "output_format": {"type": "string"},
            },
            "required": ["storyboard"],
        }

    @classmethod
    def output_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompts": {"type": "array"},
                "prompt_count": {"type": "integer"},
                "style": {"type": "string"},
            },
        }

    # ── Internal methods ─────────────────────────────────────

    def _generate_shot_prompt(
        self,
        shot: dict[str, Any],
        shot_index: int,
        characters: list[dict[str, Any]],
        scenes: list[dict[str, Any]],
        style: str,
        output_format: str,
    ) -> dict[str, Any]:
        """Generate model-specific prompt for a single shot."""
        # Base positive prompt
        positive = self._build_positive_prompt(
            shot, shot_index, characters, scenes, style
        )
        negative = self._build_negative_prompt(style)

        # Resolution
        resolution = self._determine_resolution(shot, output_format)

        # Format-specific output
        if output_format == "comfyui":
            workflow = self._build_comfyui_workflow(
                positive, negative, resolution, shot_index
            )
            return {"shot_index": shot_index, "workflow": workflow}
        elif output_format == "wan":
            return self._build_wan_prompt(shot_index, positive, negative, resolution)
        else:
            return {
                "shot_index": shot_index,
                "positive_prompt": positive,
                "negative_prompt": negative,
                "resolution": resolution,
                "steps": 25,
                "cfg_scale": 7.0,
            }

    def _build_positive_prompt(
        self,
        shot: dict[str, Any],
        shot_index: int,
        characters: list[dict[str, Any]],
        scenes: list[dict[str, Any]],
        style: str,
    ) -> str:
        """Build the positive prompt string."""
        parts = [f"({style} style)"]

        # Scene context
        scene = scenes[shot_index] if shot_index < len(scenes) else {}
        enriched = scene.get("enriched", {})
        if enriched.get("location"):
            parts.append(f"at {enriched['location']}")
        if enriched.get("time_of_day"):
            parts.append(f"during {enriched['time_of_day']}")
        if enriched.get("mood"):
            parts.append(f"{enriched['mood']} atmosphere")

        # Shot specifics
        description = shot.get("description", "")
        if description:
            parts.append(description)

        # Camera
        camera = enriched.get("camera_direction", "")
        if camera:
            parts.append(f"{camera} shot")

        # Characters
        present = enriched.get("characters_present", [])
        if present:
            char_str = ", ".join(present)
            parts.append(f"featuring {char_str}")

        # Quality tags
        parts.extend(["masterpiece", "best quality", "detailed", "sharp focus"])

        return ", ".join(parts)

    def _build_negative_prompt(self, style: str) -> str:
        """Build the negative prompt string."""
        base_negative = (
            "low quality, blurry, distorted, bad anatomy, "
            "extra fingers, missing fingers, watermark, text, "
            "signature, jpeg artifacts, oversaturated, "
            "nsfw, nude, ugly, deformed"
        )
        return base_negative

    def _determine_resolution(
        self, shot: dict[str, Any], output_format: str
    ) -> dict[str, int]:
        """Determine resolution for this shot."""
        # Default manga page ratio
        return {"width": 1024, "height": 1536}

    def _build_comfyui_workflow(
        self,
        positive: str,
        negative: str,
        resolution: dict[str, int],
        shot_index: int,
    ) -> dict[str, Any]:
        """Build a ComfyUI workflow JSON for image generation."""
        return {
            "version": 1,
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "inputs": {"ckpt_name": "flux_dev.safetensors"},
                },
                {
                    "id": 2,
                    "type": "CLIPTextEncode",
                    "inputs": {"text": positive, "clip": ["1", 1]},
                    "widgets_values": [positive],
                },
                {
                    "id": 3,
                    "type": "CLIPTextEncode",
                    "inputs": {"text": negative, "clip": ["1", 0]},
                    "widgets_values": [negative],
                },
                {
                    "id": 4,
                    "type": "EmptyLatentImage",
                    "inputs": {
                        "width": resolution["width"],
                        "height": resolution["height"],
                    },
                },
                {
                    "id": 5,
                    "type": "KSampler",
                    "inputs": {
                        "model": ["1", 0],
                        "positive": ["2", 0],
                        "negative": ["3", 0],
                        "latent_image": ["4", 0],
                        "seed": 42 + shot_index,
                        "steps": 25,
                        "cfg": 7.0,
                        "sampler_name": "euler",
                        "scheduler": "normal",
                        "denoise": 1.0,
                    },
                },
                {
                    "id": 6,
                    "type": "VAEDecode",
                    "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
                },
                {
                    "id": 7,
                    "type": "SaveImage",
                    "inputs": {
                        "filename_prefix": f"manga_shot_{shot_index:04d}"
                    },
                },
            ],
            "links": [
                [1, 2, 0, 2, 0],
                [2, 3, 0, 3, 0],
                [1, 4, 0, 4, 0],
                [1, 5, 0, 5, 0],
                [2, 5, 1, 5, 1],
                [3, 5, 2, 5, 2],
                [4, 5, 3, 5, 3],
                [5, 6, 0, 6, 0],
                [1, 6, 2, 6, 2],
                [6, 7, 0, 7, 0],
            ],
        }

    def _build_wan_prompt(
        self,
        shot_index: int,
        positive: str,
        negative: str,
        resolution: dict[str, int],
    ) -> dict[str, Any]:
        """Build a Wan video generation prompt."""
        return {
            "shot_index": shot_index,
            "positive_prompt": positive,
            "negative_prompt": negative,
            "resolution": resolution,
            "num_frames": 72,
            "fps": 24,
            "motion_bucket_id": 127,
            "model": "wan_2.1_t2v_14B",
        }
