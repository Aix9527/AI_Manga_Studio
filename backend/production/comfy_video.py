from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Any

from backend.production.comfy_adapter import (
    ComfyUIAdapter,
    ProductionError,
    ProductionErrorCode,
)
from backend.production.providers import MediaArtifact, VideoRequest
from backend.production.workflow_templates import WorkflowTemplate

logger = logging.getLogger(__name__)


def validate_workflow_schema(
    workflow: dict[str, dict[str, Any]],
    object_info: dict[str, Any],
) -> None:
    missing_nodes = sorted(
        {
            str(node.get("class_type", ""))
            for node in workflow.values()
            if node.get("class_type") not in object_info
        }
    )
    if missing_nodes:
        raise ProductionError(
            ProductionErrorCode.COMFY_WORKFLOW_INVALID,
            f"ComfyUI is missing required nodes: {', '.join(missing_nodes)}",
            {"missing_nodes": missing_nodes},
        )

    errors: list[str] = []
    for node_id, node in workflow.items():
        class_type = str(node["class_type"])
        schema = object_info[class_type]
        schema_inputs = schema.get("input", {})
        required = schema_inputs.get("required", {})
        optional = schema_inputs.get("optional", {})
        hidden = schema_inputs.get("hidden", {})
        inputs = node.get("inputs", {})

        for name in required:
            if name not in inputs:
                errors.append(f"{node_id}:{class_type} missing required input {name}")
        known_inputs = set(required) | set(optional) | set(hidden)
        for name, value in inputs.items():
            if name not in known_inputs:
                errors.append(f"{node_id}:{class_type} has unknown input {name}")
                continue
            if _is_link(value):
                source_id = str(value[0])
                if source_id not in workflow:
                    errors.append(
                        f"{node_id}:{class_type}.{name} references missing node {source_id}"
                    )
                continue
            choices = _schema_choices((required | optional).get(name))
            if choices and value not in choices:
                errors.append(
                    f"{node_id}:{class_type}.{name} has unavailable value {value!r}"
                )

    if errors:
        raise ProductionError(
            ProductionErrorCode.COMFY_WORKFLOW_INVALID,
            "LTX workflow does not match the running ComfyUI node schemas",
            {"schema_errors": errors},
        )


def _is_link(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], (str, int))
        and isinstance(value[1], int)
    )


def _schema_choices(spec: Any) -> list[Any]:
    if not isinstance(spec, list) or not spec:
        return []
    if (
        len(spec) > 1
        and isinstance(spec[1], dict)
        and spec[1].get("image_upload") is True
    ):
        return []
    if isinstance(spec[0], list):
        return spec[0]
    if len(spec) > 1 and isinstance(spec[1], dict):
        options = spec[1].get("options")
        if isinstance(options, list):
            return options
    return []


@dataclass
class LtxVideoProvider:
    adapter: ComfyUIAdapter
    template: WorkflowTemplate

    async def generate(self, request: VideoRequest) -> MediaArtifact:
        if not request.image_path.is_file():
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                f"Input image does not exist: {request.image_path}",
            )

        uploaded = await self.adapter.upload_image(request.image_path)
        workflow = self.template.render(
            image=uploaded.reference,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            seed=request.seed,
            width=request.width,
            height=request.height,
            frames=request.frames,
            fps=request.fps,
            filename_prefix=f"novel_video/{request.output_path.stem}",
        )
        comfy_artifact = await self.adapter.generate_to_file(
            workflow,
            request.output_path,
        )
        return MediaArtifact(
            path=request.output_path,
            kind="video",
            metadata={
                "provider": "ltx23",
                "source_filename": getattr(comfy_artifact, "filename", ""),
                "uploaded_image": uploaded.reference,
                "seed": request.seed,
                "width": request.width,
                "height": request.height,
                "frames": request.frames,
                "fps": request.fps,
            },
        )


@dataclass
class WanVideoProvider:
    """Wan2.2 image-to-video generation via ComfyUI.

    Wan2.2 generates cinematic-quality video from a single reference image.
    Supports motion control via motion_bucket_id (0=static, 255=maximum motion).
    Requires ComfyUI with Wan2.2 nodes installed.
    """

    adapter: ComfyUIAdapter
    template: WorkflowTemplate

    async def generate(self, request: VideoRequest) -> MediaArtifact:
        if not request.image_path.is_file():
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                f"Input image does not exist: {request.image_path}",
            )

        self._verify_models()

        # Upload the reference image to ComfyUI
        uploaded = await self.adapter.upload_image(request.image_path)

        # Upload end frame if available (FLF2V mode)
        end_frame_uploaded = None
        if request.end_frame_path and Path(request.end_frame_path).is_file():
            end_frame_uploaded = await self.adapter.upload_image(Path(request.end_frame_path))
            logger.info("FLF2V mode: uploaded end frame %s", request.end_frame_path)

        width = request.width
        height = request.height
        logger.info(
            '[WAN FINAL CONFIG] width=%s height=%s frames=%s fps=%s denoise=%s',
            width, height, request.frames, request.fps, request.denoise_strength,
        )

        # Long video jobs can exceed the default 300s poll window.
        self.adapter.timeout_seconds = max(self.adapter.timeout_seconds, 2400)

        available_values = {
            "image": uploaded.reference,
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "seed": request.seed,
            "width": width,
            "height": height,
            "frames": request.frames,
            "fps": request.fps,
            "motion_bucket_id": request.motion_bucket_id,
            "denoise_strength": request.denoise_strength,
            "filename_prefix": f"novel_video/{request.output_path.stem}",
        }

        # Add end frame reference if uploaded
        if end_frame_uploaded:
            available_values["end_frame_image"] = end_frame_uploaded.reference

        declared = set(self.template.bindings.keys())
        render_values = {k: v for k, v in available_values.items() if k in declared}

        workflow = self.template.render(**render_values)

        comfy_artifact = await self.adapter.generate_to_file(
            workflow,
            request.output_path,
        )
        return MediaArtifact(
            path=request.output_path,
            kind="video",
            metadata={
                "provider": "wan22",
                "source_filename": getattr(comfy_artifact, "filename", ""),
                "uploaded_image": uploaded.reference,
                "end_frame_image": end_frame_uploaded.reference if end_frame_uploaded else "",
                "flf2v_mode": end_frame_uploaded is not None,
                "seed": request.seed,
                "width": request.width,
                "height": request.height,
                "frames": request.frames,
                "fps": request.fps,
                "motion_bucket_id": request.motion_bucket_id,
                "denoise_strength": request.denoise_strength,
            },
        )


    def _verify_models(self) -> None:
        """Refuse to run against a damaged or unexpected model file.

        A byte-size-valid but tail-corrupted wan2.2_ti2v_5B_fp16 file made
        every generated video degrade to per-frame noise ("QR code" / snow).
        Hashes are verified lazily and cached by (path, size, mtime).
        """
        import os

        from backend.production.model_guard import verify_model_file

        models_root = Path(os.environ.get("COMFYUI_MODELS_DIR", "D:/ComfyUI/models"))
        for class_type, subfolder, input_name in (
            ("UNETLoader", "diffusion_models", "unet_name"),
            ("VAELoader", "vae", "vae_name"),
            ("CLIPLoader", "text_encoders", "clip_name"),
        ):
            name = next(
                (
                    node.get("inputs", {}).get(input_name)
                    for node in self.template.workflow.values()
                    if node.get("class_type") == class_type
                ),
                None,
            )
            if not name:
                continue
            verify_model_file(models_root / subfolder / name)
            logger.info("Model %s verified", name)
