from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.production.comfy_adapter import ComfyUIAdapter
from backend.production.providers import ImageRequest, MediaArtifact
from backend.production.workflow_templates import WorkflowTemplate


@dataclass
class FluxImageProvider:
    adapter: ComfyUIAdapter
    template: WorkflowTemplate

    async def generate(self, request: ImageRequest) -> MediaArtifact:
        available_values = {
            "prompt": request.prompt,
            "prompt_t5": request.prompt,
            "negative_prompt": request.negative_prompt,
            "negative_prompt_t5": request.negative_prompt,
            "seed": request.seed,
            "width": request.width,
            "height": request.height,
            "filename_prefix": f"novel_video/{request.output_path.stem}",
        }
        # Only pass bindings that the template actually declares
        declared = set(self.template.bindings.keys())
        render_values = {k: v for k, v in available_values.items() if k in declared}
        workflow = self.template.render(**render_values)
        comfy_artifact = await self.adapter.generate_to_file(
            workflow,
            request.output_path,
        )
        return MediaArtifact(
            path=request.output_path,
            kind="image",
            metadata={
                "provider": "flux",
                "source_filename": getattr(comfy_artifact, "filename", ""),
                "seed": request.seed,
                "width": request.width,
                "height": request.height,
            },
        )


@dataclass
class FluxImageWithConsistencyProvider:
    """FLUX image generation with IP-Adapter FaceID for character consistency.

    Uses a ComfyUI workflow that includes IPAdapterFaceID nodes to lock
    character appearance across multiple shots. Requires a reference image
    of the character.
    """

    adapter: ComfyUIAdapter
    template: WorkflowTemplate

    async def generate(self, request: ImageRequest) -> MediaArtifact:
        available_values = {
            "prompt": request.prompt,
            "prompt_t5": request.prompt,
            "negative_prompt": request.negative_prompt,
            "negative_prompt_t5": request.negative_prompt,
            "seed": request.seed,
            "width": request.width,
            "height": request.height,
            "reference_image": request.reference_image,
            "ipadapter_weight": request.ipadapter_weight,
            "filename_prefix": f"novel_video/{request.output_path.stem}",
        }

        declared = set(self.template.bindings.keys())
        render_values = {k: v for k, v in available_values.items() if k in declared}

        # Upload reference image if IP-Adapter is used
        if request.reference_image and "reference_image" in declared:
            ref_path = Path(request.reference_image)
            if ref_path.exists():
                uploaded = await self.adapter.upload_image(ref_path, subfolder="characters")
                render_values["reference_image"] = uploaded.reference

        workflow = self.template.render(**render_values)
        comfy_artifact = await self.adapter.generate_to_file(
            workflow,
            request.output_path,
        )
        return MediaArtifact(
            path=request.output_path,
            kind="image",
            metadata={
                "provider": "flux_ipadapter",
                "source_filename": getattr(comfy_artifact, "filename", ""),
                "seed": request.seed,
                "width": request.width,
                "height": request.height,
                "reference_image": request.reference_image,
                "ipadapter_weight": request.ipadapter_weight,
            },
        )
