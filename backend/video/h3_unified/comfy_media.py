from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from backend.production.comfy_adapter import (
    ComfyArtifact,
    ComfyCompletedWorkflow,
    ComfyImageReference,
    ComfyUIAdapter,
    ProductionError,
    ProductionErrorCode,
)


@dataclass
class H3ComfyMediaAdapter:
    """H3-scoped ComfyUI adapter with generic media input staging.

    ComfyUI's current ``POST /upload/image`` handler writes the uploaded file
    bytes into the selected input directory without image decoding.  H3 load
    nodes can therefore reference image, audio and video files staged through
    that route.  The behavior is isolated here instead of widening the core
    production adapter contract for unrelated providers.
    """

    base: ComfyUIAdapter = field(default_factory=ComfyUIAdapter)
    timeout_seconds: int = 900

    def __post_init__(self) -> None:
        # H3 Unified 在 16GB VRAM 目标机上会动态卸载 20GB 级模型,
        # 单次 5s T2VA 实测约 9.4 分钟; 默认 300s 会在生成中途误报超时。
        if self.timeout_seconds != getattr(self.base, "timeout_seconds", self.timeout_seconds):
            self.base.timeout_seconds = self.timeout_seconds

    async def get_object_info(self) -> dict[str, Any]:
        return await self.base.get_object_info()

    async def submit_and_wait(self, workflow: dict[str, Any], on_submitted=None) -> ComfyCompletedWorkflow:
        return await self.base.submit_and_wait(workflow, on_submitted=on_submitted)

    async def wait_for_completion(self, prompt_id: str) -> dict[str, Any]:
        return await self.base.wait_for_completion(prompt_id)

    def first_artifact(self, outputs: dict[str, Any]) -> ComfyArtifact:
        return self.base.first_artifact(outputs)

    async def download_artifact(self, artifact: ComfyArtifact) -> bytes:
        return await self.base.download_artifact(artifact)

    async def upload_image(
        self,
        path: str | Path,
        subfolder: str = "h3_unified",
    ) -> ComfyImageReference:
        return await self.base.upload_image(path, subfolder=subfolder)

    async def upload_video(
        self,
        path: str | Path,
        subfolder: str = "h3_unified",
    ) -> ComfyImageReference:
        return await self.upload_input(path, subfolder=subfolder, media_kind="video")

    async def upload_audio(
        self,
        path: str | Path,
        subfolder: str = "h3_unified",
    ) -> ComfyImageReference:
        return await self.upload_input(path, subfolder=subfolder, media_kind="audio")

    async def upload_input(
        self,
        path: str | Path,
        subfolder: str = "h3_unified",
        *,
        media_kind: str = "file",
    ) -> ComfyImageReference:
        import aiohttp

        source = Path(path)
        if not source.is_file():
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                f"H3 {media_kind} input does not exist: {source}",
            )
        _safe_subfolder(subfolder)

        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        form = aiohttp.FormData()
        try:
            with source.open("rb") as media_file:
                form.add_field(
                    "image",
                    media_file,
                    filename=source.name,
                    content_type=content_type,
                )
                form.add_field("type", "input")
                form.add_field("subfolder", subfolder)
                form.add_field("overwrite", "true")
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base.base_url}/upload/image",
                        data=form,
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as response:
                        payload = await response.json()
                        if response.status >= 400:
                            raise ProductionError(
                                ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                                f"ComfyUI rejected H3 {media_kind} upload with HTTP {response.status}",
                                payload if isinstance(payload, dict) else {},
                            )
        except ProductionError:
            raise
        except Exception as error:
            raise ProductionError(
                ProductionErrorCode.COMFY_CONNECTION_FAILED,
                f"Unable to stage H3 {media_kind} input: {error}",
            ) from error

        if not isinstance(payload, dict):
            raise ProductionError(
                ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                f"ComfyUI H3 {media_kind} upload returned an invalid response",
            )
        filename = str(payload.get("name", ""))
        uploaded_subfolder = str(payload.get("subfolder", ""))
        upload_type = str(payload.get("type", "input"))
        _safe_filename(filename)
        _safe_subfolder(uploaded_subfolder)
        if upload_type != "input":
            raise ProductionError(
                ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                f"Unexpected ComfyUI H3 upload type: {upload_type}",
            )
        return ComfyImageReference(
            filename=filename,
            subfolder=uploaded_subfolder,
            type=upload_type,
        )


def _safe_filename(value: str) -> None:
    normalized = value.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if (
        not value
        or candidate.is_absolute()
        or normalized != value
        or len(candidate.parts) != 1
        or candidate.parts[0] in ("", ".", "..")
    ):
        raise ProductionError(
            ProductionErrorCode.COMFY_WORKFLOW_INVALID,
            f"Unsafe ComfyUI H3 filename: {value!r}",
        )


def _safe_subfolder(value: str) -> None:
    if not value:
        return
    normalized = value.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if (
        candidate.is_absolute()
        or normalized != value
        or any(part in ("", ".", "..") for part in candidate.parts)
    ):
        raise ProductionError(
            ProductionErrorCode.COMFY_WORKFLOW_INVALID,
            f"Unsafe ComfyUI H3 subfolder: {value!r}",
        )
