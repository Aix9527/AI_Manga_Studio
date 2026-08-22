from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from backend.novel_video.h3_provider import (
    H3Ref2VASegmentProvider,
    H3SegmentRequest,
    H3SegmentResult,
    _SegmentPublicationLock,
)
from backend.production.comfy_adapter import ComfyArtifact, ProductionError, ProductionErrorCode

from .comfy_media import H3ComfyMediaAdapter
from .execution import H3UnifiedExecutionResult, H3UnifiedExecutionService
from .reference_bundle import H3ReferenceBundle
from .ui_state import H3Mode, H3UnifiedRequest


@dataclass
class H3UnifiedFormalSegmentProvider:
    """Adapt the H3 unified control desk to the formal novel-video provider port.

    The formal scheduler/TaskRunner remains the owner of GPU locking and the
    persisted accepted-prompt checkpoint.  This provider only translates the
    already-approved H3 picture package, executes the optional external unified
    node, and reuses the existing H3 durable video/tail publication machinery.

    Formal video/audio asset references intentionally remain fail-closed in the
    current TaskRunner.  They are supported by the general H3 unified staging
    layer but are not admitted here until the formal worker resolves and binds
    their approved project asset paths just like picture references.
    """

    adapter: Any = field(default_factory=H3ComfyMediaAdapter)
    execution: Any | None = None
    asset_resolver: Callable[[str], Any | None] | None = None
    on_prompt_submitted: Callable[..., Any] | None = None
    task_binding: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.execution is None:
            self.execution = H3UnifiedExecutionService(adapter=self.adapter)

    async def generate(self, request: H3SegmentRequest) -> H3SegmentResult:
        self._validate_request_contract(request)
        unified = self._to_unified_request(request)
        checkpoint = self._checkpoint_binding(request)

        async def accepted(prompt_id: str) -> None:
            accepted_checkpoint = {**checkpoint, "prompt_id": prompt_id}
            if self.on_prompt_submitted is None:
                return
            outcome = self.on_prompt_submitted(prompt_id, accepted_checkpoint)
            if inspect.isawaitable(outcome):
                await outcome

        result = await self.execution.execute(
            unified,
            subfolder=self._staging_subfolder(request),
            on_submitted=accepted,
        )
        return await self._materialize(result, request)

    async def resume(
        self,
        request: H3SegmentRequest,
        prompt_id: str,
        checkpoint: dict[str, Any] | None = None,
    ) -> H3SegmentResult:
        self._validate_request_contract(request)
        self._validate_resume_checkpoint(prompt_id, checkpoint)
        result = await self.execution.execute(
            self._to_unified_request(request),
            resume_prompt_id=prompt_id,
        )
        return await self._materialize(result, request)

    def _validate_request_contract(self, request: H3SegmentRequest) -> None:
        package = request.package
        if package.workflow_version not in {"h3_unified", "h3-unified", "unified"}:
            raise ProductionError(
                ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                f"H3 unified formal provider received workflow {package.workflow_version!r}",
            )
        if package.video_reference_asset_version_ids or package.audio_reference_asset_version_ids:
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                "Formal H3 unified video/audio references require approved-path binding before execution",
            )
        if len(request.picture_paths) != len(package.picture_asset_version_ids):
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                "Formal H3 unified picture paths do not match the approved package",
            )
        if any(not Path(path).is_file() for path in request.picture_paths):
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                "Formal H3 unified picture reference is missing",
            )

    def _to_unified_request(self, request: H3SegmentRequest) -> H3UnifiedRequest:
        package = request.package
        paths = [str(Path(path)) for path in request.picture_paths]
        continuity_uses_tail = package.continuity_reason in {"same_action", "same_character_new_scene"}

        tail = paths[0] if paths and continuity_uses_tail else ""
        remaining = paths[1:] if tail else paths
        character = remaining[0] if remaining else ""
        location = remaining[1] if len(remaining) > 1 else ""
        storyboard = tail or (remaining[2] if len(remaining) > 2 else "")

        references = H3ReferenceBundle(
            character_identity=character,
            location=location,
            storyboard=storyboard,
        )
        return H3UnifiedRequest(
            mode=H3Mode.REF2VA,
            prompt=package.prompt_text,
            negative_prompt=package.negative_prompt,
            references=references,
            first_frame=tail,
            aspect_ratio=package.aspect_ratio.value,
            resolution=self._resolution(package.width, package.height),
            duration_seconds=int(round(package.duration_seconds)),
            steps=12,
            seed=package.effective_seed,
            gpu_vram_gb=16,
            shot_number=0,
        )

    def _checkpoint_binding(self, request: H3SegmentRequest) -> dict[str, Any]:
        required = {"task_id", "run_id", "shot_id", "attempt_id"}
        if set(self.task_binding) != required or self.task_binding.get("shot_id") != request.package.shot_id:
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                "Formal H3 unified execution binding is incomplete or conflicts with the shot",
            )
        core = {
            **self.task_binding,
            "output_video": str(request.output_video),
            "output_tail": str(request.output_tail),
            "workflow_version": request.package.workflow_version,
            "prompt": request.package.prompt_text,
            "effective_seed": request.package.effective_seed,
            "width": request.package.width,
            "height": request.package.height,
            "picture_asset_ids": list(request.package.picture_asset_version_ids),
        }
        return {
            **core,
            "idempotency_hash": sha256(
                json.dumps(core, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        }

    def _validate_resume_checkpoint(
        self,
        prompt_id: str,
        checkpoint: dict[str, Any] | None,
    ) -> None:
        if not isinstance(checkpoint, dict):
            raise ValueError("formal H3 unified resume requires checkpoint identity")
        if checkpoint.get("prompt_id") != prompt_id:
            raise ValueError("formal H3 unified prompt identity mismatch")
        required = ("task_id", "run_id", "shot_id", "attempt_id")
        if any(checkpoint.get(key) != self.task_binding.get(key) for key in required):
            raise ValueError("formal H3 unified checkpoint identity mismatch")

    async def _materialize(
        self,
        result: H3UnifiedExecutionResult,
        request: H3SegmentRequest,
    ) -> H3SegmentResult:
        publisher = self._publisher()
        manifest = publisher._manifest_path(request)
        with _SegmentPublicationLock(publisher._lock_path(request)) as lock:
            publisher._recover_incomplete_publication(request, manifest)
            adopted = publisher._adopt_committed_publication(request, manifest)
            if adopted is not None:
                return adopted
            publisher._assert_destinations_empty(request)

            artifact = self.adapter.first_artifact(result.outputs)
            payload = await self.adapter.download_artifact(artifact)
            video_temp = publisher._write_temp_file(request.output_video, payload)
            tail_temp: Path | None = None
            try:
                media = publisher._probe_media(video_temp)
                publisher._validate_media_contract(media, request.package)
                media["quality"] = publisher._validate_decoded_quality(video_temp)
                tail_temp = publisher._extract_tail_frame(video_temp, request.output_tail, media)
                video_path, tail_path, digests = publisher._publish_pair(
                    video_temp,
                    request.output_video,
                    tail_temp,
                    request.output_tail,
                    manifest,
                    lock.token,
                    result.prompt_id,
                    publisher._manifest_binding(request),
                )
            except Exception:
                video_temp.unlink(missing_ok=True)
                if tail_temp is not None:
                    tail_temp.unlink(missing_ok=True)
                raise

        return H3SegmentResult(
            prompt_id=result.prompt_id,
            video_path=video_path,
            tail_frame_path=tail_path,
            audio_present=bool(media.get("audio")),
            comfy_output=ComfyArtifact(
                filename=artifact.filename,
                subfolder=getattr(artifact, "subfolder", ""),
                type=getattr(artifact, "type", "output"),
                media_kind=getattr(artifact, "media_kind", "videos"),
            ),
            metadata={
                "prompt_id": result.prompt_id,
                "runtime": result.runtime,
                "resumed": result.resumed,
                "media": media,
                "sha256": digests,
                "workflow": "h3_unified",
            },
        )

    def _publisher(self) -> H3Ref2VASegmentProvider:
        base_adapter = getattr(self.adapter, "base", self.adapter)
        publisher = H3Ref2VASegmentProvider(
            adapter=base_adapter,
            template=None,  # publication-only helper; template is never rendered
            asset_resolver=self.asset_resolver,
        )
        publisher.task_binding = dict(self.task_binding)
        return publisher

    def _staging_subfolder(self, request: H3SegmentRequest) -> str:
        attempt = str(self.task_binding.get("attempt_id", "attempt")).replace(":", "_")
        return f"h3_unified/formal/{request.package.shot_id}/{attempt}"

    @staticmethod
    def _resolution(width: int, height: int) -> str:
        short_side = min(int(width), int(height))
        if short_side <= 360:
            return "360p"
        if short_side <= 480:
            return "480p"
        if short_side <= 720:
            return "720p"
        return "1080p"
