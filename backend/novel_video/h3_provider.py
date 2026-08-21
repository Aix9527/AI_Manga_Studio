"""Recoverable MiniMax H3 Ref2VA generation for one novel-video segment."""

from __future__ import annotations

import json
import os
import inspect
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from hashlib import sha256
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.novel_video.models import AssetVersion, H3ReferencePackage
from backend.novel_video.storage import AtomicAssetStore
from backend.production.comfy_adapter import (
    ComfyArtifact,
    ComfyUIAdapter,
    ProductionError,
    ProductionErrorCode,
)
from backend.production.workflow_templates import WorkflowTemplate


def _rate(value: Any) -> float:
    """Decode ffprobe's rational frame-rate representation."""
    text = str(value)
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        return float(numerator) / float(denominator)
    return float(text)


@dataclass(frozen=True)
class H3SegmentRequest:
    """Approved H3 references and destinations for a single generated segment."""

    package: H3ReferencePackage
    picture_paths: tuple[Path, ...]
    output_video: Path
    output_tail: Path


@dataclass(frozen=True)
class H3SegmentResult:
    """Published media plus the ComfyUI and ffprobe evidence that produced it."""

    prompt_id: str
    video_path: Path
    tail_frame_path: Path
    audio_present: bool
    comfy_output: ComfyArtifact
    metadata: dict[str, Any]


@dataclass(frozen=True)
class _CapturedPicture:
    """Immutable approved picture bytes captured before an upload can race with a path replacement."""

    filename: str
    payload: bytes


async def reconcile_emergency_prompt_journals(
    project_roots: list[Path], repository: Any, adapter_factory: Callable[[], Any],
) -> list[dict[str, Any]]:
    """Reconcile crash journals without losing or blindly re-submitting accepted prompts."""
    formal_roots = [(root / "outputs" / "formal").resolve() for root in project_roots]
    paths = sorted({path for root in formal_roots if root.is_dir() for path in root.rglob("*.h3.emergency.json")})
    outcomes: list[dict[str, Any]] = []
    adapter: Any | None = None
    for path in paths:
        journal: dict[str, Any] | None = None
        try:
            journal = json.loads(path.read_text(encoding="utf-8"))
            if journal.get("state") in {"checkpoint_reconciled", "verified_cancelled"}:
                outcomes.append({"path": str(path), "state": journal["state"]})
                continue
            checkpoint = journal.get("checkpoint")
            prompt_id = journal.get("token")
            if not isinstance(checkpoint, dict) or not isinstance(prompt_id, str) or not prompt_id:
                raise ValueError("emergency journal identity is malformed")
            run_id, shot_id = checkpoint.get("run_id"), checkpoint.get("shot_id")
            if not isinstance(run_id, str) or not isinstance(shot_id, str):
                raise ValueError("emergency journal lacks run/shot identity")
            owning_root = next((root for root in formal_roots if path.resolve() == root or root in path.resolve().parents), None)
            outputs = [Path(str(checkpoint.get(key, ""))).resolve() for key in ("output_video", "output_tail")]
            if owning_root is None or any(output != owning_root and owning_root not in output.parents for output in outputs):
                raise ValueError("emergency journal output binding escapes project formal storage")
            repository.record_generation_prompt(
                run_id, shot_id=shot_id, prompt_id=prompt_id, checkpoint=checkpoint,
            )
            journal.update({"state": "checkpoint_reconciled", "reconciliation": {"prompt_id": prompt_id}})
        except Exception as persistence_error:
            prompt_id = journal.get("token") if isinstance(journal, dict) else None
            if not isinstance(prompt_id, str) or not prompt_id:
                outcomes.append({"path": str(path), "state": "invalid", "error": str(persistence_error)})
                continue
            try:
                adapter = adapter or adapter_factory()
                cancellation = await adapter.cancel_job(prompt_id)
                state = getattr(cancellation, "state", "uncertain")
                journal.update({"state": state, "reconciliation": {"prompt_id": prompt_id, "persistence_error": str(persistence_error)}})
            except Exception as cancel_error:
                journal.update({"state": "cancel_uncertain", "reconciliation": {"prompt_id": prompt_id, "persistence_error": str(persistence_error), "cancel_error": str(cancel_error)}})
        H3Ref2VASegmentProvider._write_manifest(path, journal)
        outcomes.append({"path": str(path), "state": journal["state"]})
    return outcomes


class _SegmentPublicationLock:
    """Cross-process advisory lock for one immutable video-and-tail destination pair."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.token = uuid.uuid4().hex
        self._file: Any | None = None

    def __enter__(self) -> "_SegmentPublicationLock":
        """Acquire the platform file lock without deleting or replacing another owner's lock file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        self._file = os.fdopen(descriptor, "r+b", buffering=0)
        if os.fstat(self._file.fileno()).st_size == 0:
            self._file.write(b"0")
            os.fsync(self._file.fileno())
        try:
            self._lock_file()
        except OSError as error:
            self._file.close()
            self._file = None
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                f"Segment publication is already active: {self.path}",
            ) from error
        self._file.seek(0)
        self._file.truncate()
        self._file.write(self.token.encode("ascii"))
        os.fsync(self._file.fileno())
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Release only this process's advisory lock while retaining the durable lock file."""
        if self._file is not None:
            self._unlock_file()
            self._file.close()
            self._file = None

    def _lock_file(self) -> None:
        """Use an OS-managed nonblocking byte lock that is released if this process crashes."""
        assert self._file is not None
        self._file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock_file(self) -> None:
        """Release the matching platform lock before closing its file descriptor."""
        assert self._file is not None
        self._file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)


@dataclass
class H3Ref2VASegmentProvider:
    """Generate and atomically publish an H3 Ref2VA segment from approved pictures."""

    adapter: ComfyUIAdapter
    template: WorkflowTemplate
    asset_store: AtomicAssetStore = field(default_factory=AtomicAssetStore)
    asset_resolver: Callable[[str], AssetVersion | None] | None = None
    object_info_fetcher: Callable[[], Any] | None = None
    on_prompt_submitted: Callable[[str], Any] | None = None
    task_binding: dict[str, Any] = field(default_factory=dict)
    _accepted_checkpoints: dict[str, dict[str, Any]] = field(default_factory=dict, init=False, repr=False)

    async def generate(self, request: H3SegmentRequest) -> H3SegmentResult:
        """Upload approved references, wait for SaveVideo, validate it, and publish both assets."""
        request = self._normalised_request(request)
        request = await self._bind_authoritative_models(request)
        captured_pictures = self._capture_approved_pictures(request)
        with _SegmentPublicationLock(self._lock_path(request)) as lock:
            manifest = self._manifest_path(request)
            self._recover_incomplete_publication(request, manifest)
            adopted = self._adopt_committed_publication(request, manifest)
            if adopted is not None:
                return adopted
            self._assert_destinations_empty(request)
            uploaded = [
                await self.adapter.upload_image_bytes(picture.payload, picture.filename)
                for picture in captured_pictures
            ]
            workflow = self._render_workflow(request, uploaded)
            checkpoint = self._checkpoint_binding(request, captured_pictures)
            completed = await self.adapter.submit_and_wait(
                workflow,
                on_submitted=lambda prompt_id: self._checkpoint_accepted_prompt(
                    prompt_id, checkpoint, workflow,
                ),
            )
            return await self._publish_completed(request, manifest, lock.token, completed, uploaded)

    async def resume(self, request: H3SegmentRequest, prompt_id: str, checkpoint: dict[str, Any] | None = None) -> H3SegmentResult:
        """Finish a checkpointed Comfy prompt without a second upload or /prompt call."""
        request = self._normalised_request(request)
        request = await self._bind_authoritative_models(request)
        if checkpoint is None:
            checkpoint = self._accepted_checkpoints.get(prompt_id)
        if self.task_binding and checkpoint is None:
            raise ProductionError(ProductionErrorCode.MEDIA_VALIDATION_FAILED, "Formal prompt resume requires its canonical checkpoint")
        if checkpoint is not None:
            expected = self._manifest_binding(request)
            actual = {key: value for key, value in checkpoint.items() if key != "prompt_id"}
            # The persisted checkpoint carries the worker execution binding
            # (task_id/run_id/shot_id/attempt_id) and the idempotency hash;
            # only the canonical core fields authenticate a resume.
            def _core(binding: dict[str, Any]) -> dict[str, Any]:
                return {
                    key: value for key, value in binding.items()
                    if key not in {"prompt_id", "task_id", "run_id", "shot_id", "attempt_id", "idempotency_hash"}
                }
            if _core(actual) != _core(expected) or checkpoint.get("prompt_id") != prompt_id:
                raise ProductionError(ProductionErrorCode.MEDIA_VALIDATION_FAILED, "Formal prompt checkpoint binding mismatch on resume")
        from backend.production.comfy_adapter import ComfyCompletedWorkflow

        with _SegmentPublicationLock(self._lock_path(request)) as lock:
            manifest = self._manifest_path(request)
            self._recover_incomplete_publication(request, manifest)
            adopted = self._adopt_committed_publication(request, manifest)
            if adopted is not None:
                return adopted
            self._assert_destinations_empty(request)
            completed = ComfyCompletedWorkflow(
                prompt_id=prompt_id,
                outputs=await self.adapter.wait_for_completion(prompt_id),
            )
            return await self._publish_completed(request, manifest, lock.token, completed, [])

    async def _bind_authoritative_models(self, request: H3SegmentRequest) -> H3SegmentRequest:
        """Preflight immediately before upload and replace only trusted model filenames."""
        if self.object_info_fetcher is None:
            return request
        object_info = self.object_info_fetcher()
        if hasattr(object_info, "__await__"):
            object_info = await object_info
        from backend.production.preflight import inspect_object_info

        report = inspect_object_info(object_info, "minimax_h3_ref2va")
        if not report.ok:
            try:
                with open(r"c:\Users\X\.trae-cn\work\6a70ba8010487f4816c62758\h3_preflight_diag.log", "a", encoding="utf-8") as _f:
                    _f.write(f"missing={report.missing} ambiguities={report.ambiguities} resolved={report.resolved}\n")
            except Exception:
                pass
            raise ProductionError(
                ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                "Authoritative H3 preflight failed before upload",
                {"missing": report.missing, "ambiguities": report.ambiguities},
            )
        resolved = dict(report.resolved)
        declared = request.package.model_registry_ids
        stale = {
            role: declared[role]
            for role, value in resolved.items()
            if role in declared and declared[role] != value
        }
        if stale:
            raise ProductionError(
                ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                "Task H3 model ids are stale relative to configured local ComfyUI",
                {"stale": stale, "resolved": resolved},
            )
        return H3SegmentRequest(
            package=request.package.model_copy(update={"model_registry_ids": resolved}),
            picture_paths=request.picture_paths,
            output_video=request.output_video,
            output_tail=request.output_tail,
        )

    def _checkpoint_binding(
        self, request: H3SegmentRequest, pictures: tuple[_CapturedPicture, ...],
    ) -> dict[str, Any]:
        """Bind a prompt to exactly one shot, inputs, output pair and model set."""
        inputs = [
            {"asset_id": asset_id, "sha256": sha256(picture.payload).hexdigest()}
            for asset_id, picture in zip(request.package.picture_asset_version_ids, pictures, strict=True)
        ]
        core = {
            "shot_id": request.package.shot_id,
            "inputs": inputs,
            "output_video": str(request.output_video),
            "output_tail": str(request.output_tail),
            "models": dict(request.package.model_registry_ids),
            "workflow_version": request.package.workflow_version,
            "prompt": request.package.prompt_text,
            "negative_prompt": request.package.negative_prompt,
            "base_seed": request.package.base_seed,
            "effective_seed": request.package.effective_seed,
            "width": request.package.width,
            "height": request.package.height,
            "fps": request.package.fps,
            "duration_seconds": request.package.duration_seconds,
            "legal_frame_count": request.package.legal_frame_count,
            "aspect_ratio": request.package.aspect_ratio.value,
            "megapixel_profile": request.package.megapixel_profile,
            "video_asset_ids": list(request.package.video_reference_asset_version_ids),
            "audio_asset_ids": list(request.package.audio_reference_asset_version_ids),
        }
        if self.task_binding:
            required = {"task_id", "run_id", "shot_id", "attempt_id"}
            if set(self.task_binding) != required or self.task_binding["shot_id"] != core["shot_id"]:
                raise ProductionError(ProductionErrorCode.MEDIA_VALIDATION_FAILED, "Formal execution binding is incomplete or conflicts with the H3 package")
            for key, value in self.task_binding.items():
                if key in core and core[key] != value:
                    raise ProductionError(ProductionErrorCode.MEDIA_VALIDATION_FAILED, f"Formal execution binding overwrites canonical field: {key}")
            core.update(self.task_binding)
        return {**core, "idempotency_hash": sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()}

    def _manifest_binding(self, request: H3SegmentRequest) -> dict[str, Any]:
        """Reconstruct the immutable binding used to authenticate adoption."""
        inputs = []
        for asset_id in request.package.picture_asset_version_ids:
            asset = self.asset_resolver(asset_id) if self.asset_resolver else None
            if not isinstance(asset, AssetVersion):
                raise ProductionError(ProductionErrorCode.MEDIA_VALIDATION_FAILED, f"Cannot bind manifest input asset: {asset_id}")
            inputs.append({"asset_id": asset_id, "sha256": asset.sha256})
        core = {"shot_id": request.package.shot_id, "inputs": inputs, "output_video": str(request.output_video), "output_tail": str(request.output_tail), "models": dict(request.package.model_registry_ids), "workflow_version": request.package.workflow_version, "prompt": request.package.prompt_text, "negative_prompt": request.package.negative_prompt, "base_seed": request.package.base_seed, "effective_seed": request.package.effective_seed, "width": request.package.width, "height": request.package.height, "fps": request.package.fps, "duration_seconds": request.package.duration_seconds, "legal_frame_count": request.package.legal_frame_count, "aspect_ratio": request.package.aspect_ratio.value, "megapixel_profile": request.package.megapixel_profile, "video_asset_ids": list(request.package.video_reference_asset_version_ids), "audio_asset_ids": list(request.package.audio_reference_asset_version_ids)}
        if self.task_binding:
            required = {"task_id", "run_id", "shot_id", "attempt_id"}
            if set(self.task_binding) != required or self.task_binding["shot_id"] != core["shot_id"]:
                raise ProductionError(ProductionErrorCode.MEDIA_VALIDATION_FAILED, "Formal execution binding is incomplete or conflicts with the H3 package")
            for key, value in self.task_binding.items():
                if key in core and core[key] != value:
                    raise ProductionError(ProductionErrorCode.MEDIA_VALIDATION_FAILED, f"Formal execution binding overwrites canonical field: {key}")
            core.update(self.task_binding)
        return {**core, "idempotency_hash": sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()}

    async def _checkpoint_accepted_prompt(self, prompt_id: str, checkpoint: dict[str, Any], workflow: dict[str, Any]) -> None:
        """Persist the accepted id or cancel/journal it so no accepted prompt is lost."""
        if self.on_prompt_submitted is None:
            return
        try:
            callback = self.on_prompt_submitted
            try:
                outcome = callback(prompt_id, checkpoint)
            except TypeError:
                outcome = callback(prompt_id)
            if inspect.isawaitable(outcome):
                await outcome
            self._accepted_checkpoints[prompt_id] = dict(checkpoint)
        except Exception:
            # The prompt exists even when the database is unavailable.  Cancel
            # that exact id best-effort and retain an emergency recovery record.
            journal = self._manifest_path_from_checkpoint(checkpoint).with_suffix(".h3.emergency.json")
            record = {
                "token": prompt_id, "state": "prompt_checkpoint_failed",
                "checkpoint": checkpoint, "workflow": workflow,
            }
            self._write_manifest(journal, record)
            try:
                cancellation = await self.adapter.cancel_job(prompt_id)
                record["state"] = getattr(cancellation, "state", "cancel_uncertain")
            except Exception as cancel_error:
                record["state"] = "cancel_uncertain"
                record["cancel_error"] = str(cancel_error)
            self._write_manifest(journal, record)
            raise

    @staticmethod
    def _manifest_path_from_checkpoint(checkpoint: dict[str, Any]) -> Path:
        return Path(str(checkpoint["output_video"]))

    async def _publish_completed(self, request: H3SegmentRequest, manifest: Path, token: str, completed: Any, uploaded: list[Any]) -> H3SegmentResult:
        # ComfyUI 0.30.2 SaveVideo emits animated mp4 under the "images"
        # channel (with animated=true), so that channel must be accepted too.
        artifact = self.adapter.artifact_from_node(
            completed.outputs, self._save_video_node_id(),
            media_kinds=("videos", "gifs", "images"),
        )
        video_temp = self._write_temp_file(request.output_video, await self.adapter.download_artifact(artifact))
        tail_temp: Path | None = None
        try:
            media = self._probe_media(video_temp)
            self._validate_media_contract(media, request.package)
            media["quality"] = self._validate_decoded_quality(video_temp)
            tail_temp = self._extract_tail_frame(video_temp, request.output_tail, media)
            video_path, tail_path, digests = self._publish_pair(video_temp, request.output_video, tail_temp, request.output_tail, manifest, token, completed.prompt_id, self._manifest_binding(request))
        except Exception:
            video_temp.unlink(missing_ok=True)
            if tail_temp is not None:
                tail_temp.unlink(missing_ok=True)
            raise
        return H3SegmentResult(
            prompt_id=completed.prompt_id, video_path=video_path, tail_frame_path=tail_path,
            audio_present=bool(media["audio"]), comfy_output=artifact,
            metadata={"prompt_id": completed.prompt_id,
                      "comfy_output": {"filename": artifact.filename, "subfolder": artifact.subfolder, "type": artifact.type, "media_kind": artifact.media_kind},
                      "uploaded_references": [reference.reference for reference in uploaded], "media": media,
                      "models": dict(request.package.model_registry_ids), "sha256": digests},
        )

    def _capture_approved_pictures(
        self,
        request: H3SegmentRequest,
    ) -> tuple[_CapturedPicture, ...]:
        """Capture each authoritative picture once, verify its bytes, and return only that immutable payload."""
        asset_ids = request.package.picture_asset_version_ids
        if request.package.video_reference_asset_version_ids or request.package.audio_reference_asset_version_ids:
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                "Formal H3 video/audio references are unsupported until authoritative upload bindings exist",
            )
        if not asset_ids or len(asset_ids) > 3 or len(request.picture_paths) != len(asset_ids):
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                "Picture paths must match the one-to-three approved package asset ids",
            )
        if self.asset_resolver is None:
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                "H3 provider requires an authoritative approved asset resolver",
            )
        captured: list[_CapturedPicture] = []
        for expected_id, picture_path in zip(asset_ids, request.picture_paths, strict=True):
            asset = self.asset_resolver(expected_id)
            if not isinstance(asset, AssetVersion) or asset.id != expected_id:
                raise ProductionError(
                    ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                    f"Approved picture asset cannot be resolved: {expected_id}",
                )
            if asset.state != "approved":
                raise ProductionError(
                    ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                    f"Picture asset is not approved: {asset.id}",
                )
            if not picture_path.is_file() or not asset.path.is_file():
                raise ProductionError(
                    ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                    f"Input picture does not exist: {picture_path}",
                )
            if asset.path.resolve() != picture_path.resolve():
                raise ProductionError(
                    ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                    f"Input picture path does not match approved asset: {asset.id}",
                )
            try:
                payload = picture_path.read_bytes()
            except OSError as error:
                raise ProductionError(
                    ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                    f"Unable to capture approved input picture: {picture_path}",
                ) from error
            if not payload or sha256(payload).hexdigest() != asset.sha256:
                raise ProductionError(
                    ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                    f"Input picture digest does not match approved asset: {asset.id}",
                )
            captured.append(_CapturedPicture(filename=picture_path.name, payload=payload))
        if request.output_video == request.output_tail:
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                "Video and tail destinations must differ",
            )
        return tuple(captured)

    @staticmethod
    def _normalised_request(request: H3SegmentRequest) -> H3SegmentRequest:
        """Resolve input and output paths once so aliases share validation and lock identity."""
        return H3SegmentRequest(
            package=request.package,
            picture_paths=tuple(Path(path).resolve() for path in request.picture_paths),
            output_video=Path(request.output_video).resolve(),
            output_tail=Path(request.output_tail).resolve(),
        )

    @staticmethod
    def _file_digest(path: Path) -> str:
        """Calculate the content digest used to bind an asset record to its file."""
        digest = sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _assert_destinations_empty(request: H3SegmentRequest) -> None:
        """Keep finalized segment paths immutable after incomplete-work recovery has run."""
        for destination in (request.output_video, request.output_tail):
            if destination.exists():
                raise FileExistsError(f"asset destination already exists: {destination}")

    def _render_workflow(self, request: H3SegmentRequest, uploaded: list[Any]) -> dict[str, Any]:
        """Render the fixed three-slot workflow with only links for uploaded pictures."""
        values = {
            name: self._template_default(name) for name in self.template.bindings
        }
        values.update(
            {
                "prompt": request.package.prompt_text,
                "picture_1": uploaded[0].reference if len(uploaded) >= 1 else "",
                "picture_2": uploaded[1].reference if len(uploaded) >= 2 else "",
                "picture_3": uploaded[2].reference if len(uploaded) >= 3 else "",
                "ref_images": [[str(7 + index), 0] for index in range(len(uploaded))],
                "width": request.package.width,
                "height": request.package.height,
                "frames": request.package.legal_frame_count,
                "seed": request.package.effective_seed,
                "fps": request.package.fps,
                "filename_prefix": f"novel_video/{request.output_video.stem}",
            }
        )
        for name in ("diffusion_model", "text_encoder", "video_vae", "audio_vae"):
            if name in self.template.bindings:
                model_id = request.package.model_registry_ids.get(name)
                if not model_id:
                    raise ProductionError(
                        ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                        f"Missing resolved H3 model id: {name}",
                    )
                values[name] = model_id
        return self.template.render(**values)

    def _template_default(self, binding: str) -> Any:
        """Read the template's declared default for a binding not owned by the request."""
        node_id, input_name = self.template.bindings[binding][0]
        return self.template.workflow[node_id]["inputs"][input_name]

    def _save_video_node_id(self) -> str:
        """Find the SaveVideo node whose history output is the segment artifact."""
        for node_id, node in self.template.workflow.items():
            if node.get("class_type") == "SaveVideo":
                return node_id
        raise ProductionError(
            ProductionErrorCode.COMFY_NO_OUTPUT,
            "H3 workflow has no SaveVideo node",
        )

    @staticmethod
    def _lock_path(request: H3SegmentRequest) -> Path:
        """Derive a stable lock path from both immutable output destinations."""
        identity = "\0".join(
            (str(request.output_video.resolve()), str(request.output_tail.resolve()))
        )
        return request.output_video.parent / f".{sha256(identity.encode()).hexdigest()}.h3.lock"

    @staticmethod
    def _manifest_path(request: H3SegmentRequest) -> Path:
        """Store one durable transaction manifest beside the segment's video destination."""
        identity = "\0".join(
            (str(request.output_video.resolve()), str(request.output_tail.resolve()))
        )
        return request.output_video.parent / f".{sha256(identity.encode()).hexdigest()}.h3.transaction.json"

    def _recover_incomplete_publication(
        self,
        request: H3SegmentRequest,
        manifest_path: Path,
    ) -> None:
        """Block unsafe reuse of a segment whose durable transaction did not reach commit."""
        if not manifest_path.is_file():
            return
        manifest = self._read_manifest(manifest_path, request)
        if manifest["state"] == "committed":
            return
        if not request.output_video.exists() and not request.output_tail.exists():
            self._supersede_manifest(manifest_path, manifest["token"])
            return
        manifest["state"] = "recovery_required"
        manifest["recovery"] = {
            "video_exists": request.output_video.exists(),
            "tail_exists": request.output_tail.exists(),
            "action": "preserved_for_manual_or_quarantine_handling",
        }
        self._write_manifest(manifest_path, manifest)
        raise ProductionError(
            ProductionErrorCode.MEDIA_VALIDATION_FAILED,
            "Incomplete H3 publication requires manual or quarantine recovery",
            {"manifest_path": str(manifest_path), "token": manifest["token"]},
        )

    def _adopt_committed_publication(self, request: H3SegmentRequest, manifest_path: Path) -> H3SegmentResult | None:
        """Return a verified already-published pair after a DB-only crash."""
        if not manifest_path.is_file():
            return None
        manifest = self._read_manifest(manifest_path, request)
        if manifest.get("state") != "committed":
            return None
        if not request.output_video.is_file() or not request.output_tail.is_file():
            raise ProductionError(ProductionErrorCode.MEDIA_VALIDATION_FAILED, "Committed H3 manifest is missing its paired files")
        if self._file_digest(request.output_video) != manifest["digests"]["video"] or self._file_digest(request.output_tail) != manifest["digests"]["tail"]:
            raise ProductionError(ProductionErrorCode.MEDIA_VALIDATION_FAILED, "Committed H3 manifest digest mismatch")
        prompt_id = manifest.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ProductionError(ProductionErrorCode.MEDIA_VALIDATION_FAILED, "Committed H3 manifest lacks prompt binding")
        binding = manifest.get("binding")
        if not isinstance(binding, dict) or binding != self._manifest_binding(request):
            raise ProductionError(ProductionErrorCode.MEDIA_VALIDATION_FAILED, "Committed H3 manifest binding mismatch")
        media = self._probe_media(request.output_video)
        self._validate_media_contract(media, request.package)
        media["quality"] = self._validate_decoded_quality(request.output_video)
        return H3SegmentResult(prompt_id, request.output_video, request.output_tail, bool(media["audio"]), ComfyArtifact(request.output_video.name, media_kind="videos"), {"prompt_id": prompt_id, "media": media, "sha256": dict(manifest["digests"]), "recovery": {"adopted_committed_manifest": True}})

    @staticmethod
    def _supersede_manifest(manifest_path: Path, token: str) -> Path:
        """Archive an empty prepared transaction for audit before safely starting a new one."""
        archive_path = manifest_path.with_name(
            f"{manifest_path.name}.superseded.{token}.{uuid.uuid4().hex}.json"
        )
        manifest_path.replace(archive_path)
        H3Ref2VASegmentProvider._durability_barrier(archive_path)
        return archive_path

    def _read_manifest(
        self,
        manifest_path: Path,
        request: H3SegmentRequest,
    ) -> dict[str, Any]:
        """Validate a durable manifest before using it to remove any output file."""
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                f"Invalid H3 publication manifest: {manifest_path}",
            ) from error
        destinations = {
            "video": str(request.output_video.resolve()),
            "tail": str(request.output_tail.resolve()),
        }
        digests = manifest.get("digests") if isinstance(manifest, dict) else None
        if (
            not isinstance(manifest, dict)
            or not isinstance(manifest.get("token"), str)
            or not isinstance(manifest.get("state"), str)
            or manifest.get("destinations") != destinations
            or not isinstance(digests, dict)
            or any(
                not isinstance(digests.get(kind), str)
                or len(digests[kind]) != 64
                for kind in ("video", "tail")
            )
        ):
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                f"Unsafe H3 publication manifest: {manifest_path}",
            )
        return manifest

    @staticmethod
    def _write_manifest(manifest_path: Path, manifest: dict[str, Any]) -> None:
        """Durably replace transaction state so a crash never fabricates a committed pair."""
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            suffix=".json.tmp",
            prefix=f".{manifest_path.stem}.",
            dir=manifest_path.parent,
            mode="w",
            encoding="utf-8",
            delete=False,
        ) as file:
            json.dump(manifest, file, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
            temp_path = Path(file.name)
        temp_path.replace(manifest_path)
        H3Ref2VASegmentProvider._durability_barrier(manifest_path)

    @staticmethod
    def _durability_barrier(path: Path) -> None:
        """Flush a file and its parent directory when the platform exposes those durability barriers."""
        try:
            with path.open("rb") as file:
                os.fsync(file.fileno())
        except OSError:
            return
        if os.name == "nt":
            return
        try:
            descriptor = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)

    @staticmethod
    def _write_temp_file(destination: Path, payload: bytes) -> Path:
        """Stage downloaded media beside its final destination for atomic publication."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            suffix=destination.suffix,
            prefix=f".{destination.stem}.",
            dir=destination.parent,
            delete=False,
        ) as file:
            file.write(payload)
            return Path(file.name)

    @staticmethod
    def _probe_media(video_path: Path) -> dict[str, Any]:
        """Collect ffprobe evidence for both video and audio streams before publishing."""
        probe_binary = os.environ.get(
            "AI_MANGA_FFPROBE",
            r"C:\Users\X\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\bin\ffprobe.cmd",
        )
        try:
            result = subprocess.run(
                [
                    probe_binary,
                    "-v",
                    "error",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    str(video_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode:
                raise ValueError(result.stderr.strip() or "ffprobe failed")
            probe = json.loads(result.stdout)
        except (FileNotFoundError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                f"Unable to probe generated video: {error}",
            ) from error
        streams = probe.get("streams", [])
        video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        if not isinstance(video, dict):
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                "Generated ComfyUI output has no video stream",
            )
        audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
        return {
            "video": {
                "codec": video.get("codec_name", ""),
                "width": video.get("width", 0),
                "height": video.get("height", 0),
                "fps": video.get("r_frame_rate", ""),
                "avg_fps": video.get("avg_frame_rate", ""),
                "frames": video.get("nb_frames", ""),
                "duration": probe.get("format", {}).get("duration", ""),
            },
            "audio": (
                {
                    "codec": audio.get("codec_name", ""),
                    "sample_rate": audio.get("sample_rate", ""),
                    "channels": audio.get("channels", 0),
                }
                if isinstance(audio, dict)
                else {}
            ),
        }

    @staticmethod
    def _validate_media_contract(media: dict[str, Any], package: H3ReferencePackage) -> None:
        """Require decoded output to satisfy the approved H3 dimensions, cadence, duration, frames, and audio."""
        video = media.get("video", {})
        audio = media.get("audio", {})
        expected_duration = package.duration_seconds
        try:
            fps = _rate(video.get("avg_fps") or video.get("fps"))
            duration = float(video.get("duration"))
            frames = int(video.get("frames"))
        except (TypeError, ValueError, ZeroDivisionError) as error:
            raise ProductionError(ProductionErrorCode.MEDIA_VALIDATION_FAILED, "Generated media lacks decodable timing evidence") from error
        errors = []
        if (int(video.get("width", 0)), int(video.get("height", 0))) != (package.width, package.height):
            errors.append("dimensions")
        if abs(fps - package.fps) > 0.05:
            errors.append("fps")
        if abs(duration - expected_duration) > 0.25:
            errors.append("duration")
        if abs(frames - package.legal_frame_count) > 2:
            errors.append("frames")
        if not audio.get("codec") or int(audio.get("channels", 0)) < 1:
            errors.append("audio")
        if errors:
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                f"Generated media violates approved H3 contract: {', '.join(errors)}",
                {"media": media, "expected": {"width": package.width, "height": package.height, "fps": package.fps, "duration": expected_duration, "frames": package.legal_frame_count, "audio_required": True}},
            )

    @staticmethod
    def _validate_decoded_quality(video_path: Path) -> dict[str, Any]:
        """Reject decode-complete but unusable black/frozen/silent candidates."""
        try:
            video_check = subprocess.run(
                [os.environ.get("AI_MANGA_FFMPEG", r"C:\Users\X\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\bin\ffmpeg.cmd"), "-v", "info", "-i", str(video_path), "-vf", "blackdetect=d=1:pix_th=0.10,freezedetect=n=0.001:d=1", "-f", "null", "-"],
                check=False, capture_output=True, text=True, timeout=45,
            )
            audio_check = subprocess.run(
                [os.environ.get("AI_MANGA_FFMPEG", r"C:\Users\X\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\bin\ffmpeg.cmd"), "-v", "info", "-i", str(video_path), "-af", "volumedetect", "-f", "null", "-"],
                check=False, capture_output=True, text=True, timeout=45,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            raise ProductionError(ProductionErrorCode.MEDIA_VALIDATION_FAILED, f"Unable to decode media quality evidence: {error}") from error
        video_log, audio_log = video_check.stderr, audio_check.stderr
        frozen = "freeze_start" in video_log
        black = "black_start" in video_log
        import re
        level = re.search(r"max_volume:\s*(-?[\d.]+) dB", audio_log)
        max_db = float(level.group(1)) if level else float("-inf")
        if video_check.returncode or audio_check.returncode or black or frozen or max_db <= -50.0:
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                "Generated media fails decoded black/freeze/audio quality gate",
                {"black": black, "frozen": frozen, "max_volume_db": max_db, "freeze_threshold_seconds": 1, "silence_max_db": -50.0},
            )
        return {"black": False, "frozen": False, "max_volume_db": max_db, "freeze_threshold_seconds": 1, "silence_max_db": -50.0}

    @staticmethod
    def _extract_tail_frame(video_path: Path, destination: Path, media: dict[str, Any]) -> Path:
        """Extract the last video frame into a staged image adjacent to its final path."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            suffix=".png",
            prefix=f".{destination.stem}.",
            dir=destination.parent,
            delete=False,
        ) as file:
            tail_temp = Path(file.name)
        try:
            result = subprocess.run(
                [
                    os.environ.get("AI_MANGA_FFMPEG", r"C:\Users\X\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\bin\ffmpeg.cmd"),
                    "-y",
                    "-v",
                    "error",
                    "-sseof",
                    "-1",
                    "-i",
                    str(video_path),
                    "-vf",
                    "reverse",
                    "-frames:v",
                    "1",
                    str(tail_temp),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode or not tail_temp.is_file() or tail_temp.stat().st_size == 0:
                raise ValueError(result.stderr.strip() or "ffmpeg did not write a tail frame")
            return tail_temp
        except (FileNotFoundError, ValueError, subprocess.TimeoutExpired) as error:
            tail_temp.unlink(missing_ok=True)
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                f"Unable to extract generated tail frame: {error}",
            ) from error

    def _publish_pair(
        self,
        video_temp: Path,
        video_destination: Path,
        tail_temp: Path,
        tail_destination: Path,
        manifest_path: Path,
        token: str,
        prompt_id: str,
        binding: dict[str, Any],
    ) -> tuple[Path, Path, dict[str, str]]:
        """Publish a durable prepared/committed pair with verified rollback on ordinary failure."""
        if video_destination.exists() or tail_destination.exists():
            raise FileExistsError("a finalized segment asset already exists")
        manifest = {
            "token": token,
            "prompt_id": prompt_id,
            "binding": binding,
            "state": "prepared",
            "destinations": {
                "video": str(video_destination.resolve()),
                "tail": str(tail_destination.resolve()),
            },
            "digests": {
                "video": self._file_digest(video_temp),
                "tail": self._file_digest(tail_temp),
            },
        }
        self._write_manifest(manifest_path, manifest)
        try:
            video_path, video_digest = self.asset_store.publish(video_temp, video_destination)
            if self._file_digest(video_path) != manifest["digests"]["video"]:
                raise ProductionError(
                    ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                    "Published video no longer matches its prepared transaction digest",
                )
            self._durability_barrier(video_path)
            manifest["state"] = "video_published"
            self._write_manifest(manifest_path, manifest)
            tail_path, tail_digest = self.asset_store.publish(tail_temp, tail_destination)
            if self._file_digest(tail_path) != manifest["digests"]["tail"]:
                raise ProductionError(
                    ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                    "Published tail no longer matches its prepared transaction digest",
                )
            self._durability_barrier(tail_path)
        except Exception:
            manifest["state"] = "recovery_required"
            manifest["recovery"] = {
                "video_exists": video_destination.exists(),
                "tail_exists": tail_destination.exists(),
                "action": "preserved_for_manual_or_quarantine_handling",
            }
            self._write_manifest(manifest_path, manifest)
            raise
        manifest["state"] = "committed"
        self._write_manifest(manifest_path, manifest)
        return video_path, tail_path, {"video": video_digest, "tail": tail_digest}
