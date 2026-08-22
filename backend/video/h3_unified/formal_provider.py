from __future__ import annotations

import hmac
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
from backend.novel_video.models import AssetVersion
from backend.production.comfy_adapter import ComfyArtifact, ProductionError, ProductionErrorCode

from .comfy_media import H3ComfyMediaAdapter
from .execution import H3UnifiedExecutionResult, H3UnifiedExecutionService
from .reference_bundle import H3ReferenceBundle
from .ui_state import H3Mode, H3UnifiedRequest


@dataclass
class H3UnifiedFormalSegmentProvider:
    """Adapt the H3 unified control desk to the formal novel-video provider port.

    The formal scheduler/TaskRunner remains the owner of GPU locking and the
    persisted accepted-prompt checkpoint.  This provider translates only
    repository-authenticated project assets, revalidates their bytes before
    staging, and reuses the existing H3 durable video/tail publication path.
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
        self._validate_resume_checkpoint(prompt_id, checkpoint, request)
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
        picture_paths = tuple(Path(path) for path in request.picture_paths)
        video_paths = tuple(Path(path) for path in getattr(request, "video_paths", ()))
        audio_paths = tuple(Path(path) for path in getattr(request, "audio_paths", ()))
        if len(picture_paths) != len(package.picture_asset_version_ids):
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                "Formal H3 unified picture paths do not match the approved package",
            )
        if len(video_paths) != len(package.video_reference_asset_version_ids):
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                "Formal H3 unified video paths do not match the approved package",
            )
        if len(audio_paths) != len(package.audio_reference_asset_version_ids):
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                "Formal H3 unified audio paths do not match the approved package",
            )
        if any(not path.is_file() for path in (*picture_paths, *video_paths, *audio_paths)):
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                "Formal H3 unified reference media is missing",
            )
        if package.video_reference_asset_version_ids or package.audio_reference_asset_version_ids:
            if self.asset_resolver is None:
                raise ProductionError(
                    ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                    "Formal H3 unified media references require an authoritative asset resolver",
                )
            self._bound_inputs(package.video_reference_asset_version_ids, video_paths, "video")
            self._bound_inputs(package.audio_reference_asset_version_ids, audio_paths, "audio")

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
            videos=tuple(str(Path(path)) for path in getattr(request, "video_paths", ())),
            audios=tuple(str(Path(path)) for path in getattr(request, "audio_paths", ())),
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
        picture_paths = tuple(Path(path) for path in request.picture_paths)
        video_paths = tuple(Path(path) for path in getattr(request, "video_paths", ()))
        audio_paths = tuple(Path(path) for path in getattr(request, "audio_paths", ()))
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
            "video_asset_ids": list(request.package.video_reference_asset_version_ids),
            "audio_asset_ids": list(request.package.audio_reference_asset_version_ids),
            "picture_inputs": self._checkpoint_inputs(
                request.package.picture_asset_version_ids, picture_paths, "picture"
            ),
            "video_inputs": self._checkpoint_inputs(
                request.package.video_reference_asset_version_ids, video_paths, "video"
            ),
            "audio_inputs": self._checkpoint_inputs(
                request.package.audio_reference_asset_version_ids, audio_paths, "audio"
            ),
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
        request: H3SegmentRequest | None = None,
    ) -> None:
        if not isinstance(checkpoint, dict):
            raise ValueError("formal H3 unified resume requires checkpoint identity")
        if checkpoint.get("prompt_id") != prompt_id:
            raise ValueError("formal H3 unified prompt identity mismatch")
        required = ("task_id", "run_id", "shot_id", "attempt_id")
        if any(checkpoint.get(key) != self.task_binding.get(key) for key in required):
            raise ValueError("formal H3 unified checkpoint identity mismatch")
        if request is not None and (
            request.package.video_reference_asset_version_ids
            or request.package.audio_reference_asset_version_ids
        ):
            expected = self._checkpoint_binding(request)
            if checkpoint.get("idempotency_hash") != expected["idempotency_hash"]:
                raise ValueError("formal H3 unified checkpoint media binding mismatch")

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
        publisher = _H3UnifiedPublicationProvider(
            adapter=base_adapter,
            template=None,  # publication-only helper; template is never rendered
            asset_resolver=self.asset_resolver,
        )
        publisher.task_binding = dict(self.task_binding)
        return publisher

    def _bound_inputs(
        self,
        asset_ids: list[str],
        paths: tuple[Path, ...],
        media_kind: str,
    ) -> list[dict[str, str]]:
        if len(asset_ids) != len(paths):
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                f"Formal H3 unified {media_kind} binding count mismatch",
            )
        bound: list[dict[str, str]] = []
        for asset_id, path in zip(asset_ids, paths, strict=True):
            asset = self.asset_resolver(asset_id) if self.asset_resolver else None
            if not isinstance(asset, AssetVersion):
                raise ProductionError(
                    ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                    f"Cannot resolve approved H3 unified {media_kind} asset: {asset_id}",
                )
            if Path(asset.path) != Path(path):
                raise ProductionError(
                    ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                    f"Formal H3 unified {media_kind} path differs from approved asset",
                )
            if media_kind == "video" and asset.kind != "video":
                raise ProductionError(
                    ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                    "Formal H3 unified video asset kind is incompatible",
                )
            if media_kind == "audio" and not _is_audio_kind(asset.kind):
                raise ProductionError(
                    ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                    "Formal H3 unified audio asset kind is incompatible",
                )
            digest = _file_sha256(path)
            if not hmac.compare_digest(digest, asset.sha256):
                raise ProductionError(
                    ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                    f"Formal H3 unified {media_kind} bytes no longer match approved asset",
                )
            bound.append({"asset_id": asset_id, "sha256": digest})
        return bound

    def _checkpoint_inputs(
        self,
        asset_ids: list[str],
        paths: tuple[Path, ...],
        media_kind: str,
    ) -> list[dict[str, str]]:
        if not asset_ids:
            return []
        if self.asset_resolver is not None:
            return self._bound_inputs(asset_ids, paths, media_kind)
        return [
            {"asset_id": asset_id, "sha256": _file_sha256(path)}
            for asset_id, path in zip(asset_ids, paths, strict=True)
        ]

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


class _H3UnifiedPublicationProvider(H3Ref2VASegmentProvider):
    """Extend the durable publication manifest with media-version digests."""

    def _manifest_binding(self, request: H3SegmentRequest) -> dict[str, Any]:
        binding = dict(super()._manifest_binding(request))
        binding.pop("idempotency_hash", None)
        video_paths = tuple(Path(path) for path in getattr(request, "video_paths", ()))
        audio_paths = tuple(Path(path) for path in getattr(request, "audio_paths", ()))
        binding["video_inputs"] = self._manifest_media_inputs(
            request.package.video_reference_asset_version_ids, video_paths, "video"
        )
        binding["audio_inputs"] = self._manifest_media_inputs(
            request.package.audio_reference_asset_version_ids, audio_paths, "audio"
        )
        return {
            **binding,
            "idempotency_hash": sha256(
                json.dumps(binding, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        }

    def _manifest_media_inputs(
        self,
        asset_ids: list[str],
        paths: tuple[Path, ...],
        media_kind: str,
    ) -> list[dict[str, str]]:
        if len(asset_ids) != len(paths):
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                f"Formal H3 unified manifest {media_kind} binding count mismatch",
            )
        result: list[dict[str, str]] = []
        for asset_id, path in zip(asset_ids, paths, strict=True):
            asset = self.asset_resolver(asset_id) if self.asset_resolver else None
            if not isinstance(asset, AssetVersion) or Path(asset.path) != path:
                raise ProductionError(
                    ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                    f"Cannot bind H3 unified manifest {media_kind} asset: {asset_id}",
                )
            digest = _file_sha256(path)
            if not hmac.compare_digest(digest, asset.sha256):
                raise ProductionError(
                    ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                    f"H3 unified manifest {media_kind} bytes do not verify",
                )
            result.append({"asset_id": asset_id, "sha256": digest})
        return result


def _is_audio_kind(kind: str) -> bool:
    return kind == "audio" or kind.endswith("_audio")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
