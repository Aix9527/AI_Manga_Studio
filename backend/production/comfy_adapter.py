from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any


class ProductionErrorCode(str, Enum):
    COMFY_NO_OUTPUT = "COMFY_NO_OUTPUT"
    COMFY_TIMEOUT = "COMFY_TIMEOUT"
    COMFY_CONNECTION_FAILED = "COMFY_CONNECTION_FAILED"
    COMFY_EXECUTION_FAILED = "COMFY_EXECUTION_FAILED"
    COMFY_OOM = "COMFY_OOM"
    COMFY_WORKFLOW_INVALID = "COMFY_WORKFLOW_INVALID"
    MEDIA_VALIDATION_FAILED = "MEDIA_VALIDATION_FAILED"
    INPUT_PARSE_FAILED = "INPUT_PARSE_FAILED"
    UNKNOWN = "UNKNOWN"


class ProductionError(Exception):
    def __init__(
        self,
        code: ProductionErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"[{code}] {message}")


class ComfyUIState(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    OOM = "oom"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True)
class ComfyArtifact:
    filename: str
    subfolder: str = ""
    type: str = "output"
    media_kind: str = ""


@dataclass(frozen=True)
class ComfyImageReference:
    filename: str
    subfolder: str = ""
    type: str = "input"

    @property
    def reference(self) -> str:
        if self.subfolder:
            return f"{self.subfolder}/{self.filename}"
        return self.filename


@dataclass(frozen=True)
class ComfyCompletedWorkflow:
    """A terminal ComfyUI history record paired with its prompt identifier."""

    prompt_id: str
    outputs: dict[str, Any]


@dataclass(frozen=True)
class CancelJobResult:
    """Exact-prompt cancellation outcome backed by queue and history evidence."""

    prompt_id: str
    state: str
    was_running: bool = False


@dataclass
class ComfyUIAdapter:
    base_url: str = "http://127.0.0.1:8188"
    timeout_seconds: int = 300
    poll_interval: float = 2.0
    state: ComfyUIState = ComfyUIState.DISCONNECTED
    _last_error: str = ""

    async def is_available(self) -> bool:
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/system_stats",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status == 200:
                        self.state = ComfyUIState.IDLE
                        return True
        except Exception as error:
            self._last_error = str(error)
            self.state = ComfyUIState.DISCONNECTED
        return False

    async def get_object_info(self) -> dict[str, Any]:
        """Read the configured ComfyUI node catalogue without submitting work."""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/object_info",
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    payload = await response.json()
                    if response.status >= 400 or not isinstance(payload, dict):
                        raise ProductionError(
                            ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                            f"ComfyUI object_info is invalid (HTTP {response.status})",
                        )
                    return payload
        except ProductionError:
            raise
        except Exception as error:
            raise ProductionError(
                ProductionErrorCode.COMFY_CONNECTION_FAILED,
                f"Unable to read ComfyUI object_info: {error}",
            ) from error

    async def submit_workflow(self, workflow: dict[str, Any]) -> str:
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/prompt",
                    json={"prompt": workflow},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    payload = await response.json()
                    if response.status >= 400:
                        raise ProductionError(
                            ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                            f"ComfyUI rejected workflow with HTTP {response.status}",
                            payload if isinstance(payload, dict) else {},
                        )
                    prompt_id = payload.get("prompt_id", "")
                    if not prompt_id:
                        raise ProductionError(
                            ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                            "No prompt_id in ComfyUI response",
                            payload if isinstance(payload, dict) else {},
                        )
                    self.state = ComfyUIState.BUSY
                    return prompt_id
        except ProductionError:
            raise
        except Exception as error:
            self.state = ComfyUIState.DISCONNECTED
            raise ProductionError(
                ProductionErrorCode.COMFY_CONNECTION_FAILED,
                str(error),
            ) from error

    async def upload_image(
        self,
        image_path: str | Path,
        subfolder: str = "novel_video",
    ) -> ComfyImageReference:
        import aiohttp

        path = Path(image_path)
        if not path.is_file():
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                f"Input image does not exist: {path}",
            )
        _safe_relative_path(subfolder, allow_empty=True)

        form = aiohttp.FormData()
        try:
            with path.open("rb") as image_file:
                form.add_field(
                    "image",
                    image_file,
                    filename=path.name,
                    content_type="application/octet-stream",
                )
                form.add_field("type", "input")
                form.add_field("subfolder", subfolder)
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/upload/image",
                        data=form,
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as response:
                        payload = await response.json()
                        if response.status >= 400:
                            raise ProductionError(
                                ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                                f"ComfyUI rejected image upload with HTTP {response.status}",
                                payload if isinstance(payload, dict) else {},
                            )
        except ProductionError:
            raise
        except Exception as error:
            raise ProductionError(
                ProductionErrorCode.COMFY_CONNECTION_FAILED,
                str(error),
            ) from error

        if not isinstance(payload, dict):
            raise ProductionError(
                ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                "ComfyUI image upload returned an invalid response",
            )
        filename = str(payload.get("name", ""))
        uploaded_subfolder = str(payload.get("subfolder", ""))
        upload_type = str(payload.get("type", "input"))
        _safe_relative_path(filename)
        _safe_relative_path(uploaded_subfolder, allow_empty=True)
        if upload_type != "input":
            raise ProductionError(
                ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                f"Unexpected ComfyUI upload type: {upload_type}",
            )
        return ComfyImageReference(
            filename=filename,
            subfolder=uploaded_subfolder,
            type=upload_type,
        )

    async def upload_image_bytes(
        self,
        payload: bytes,
        filename: str,
        subfolder: str = "novel_video",
    ) -> ComfyImageReference:
        """Upload an already verified image payload without reopening a mutable source path."""
        import aiohttp

        if not isinstance(payload, bytes) or not payload:
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                "Image upload payload is missing or empty",
            )
        _safe_relative_path(filename)
        _safe_relative_path(subfolder, allow_empty=True)
        form = aiohttp.FormData()
        form.add_field(
            "image",
            payload,
            filename=filename,
            content_type="application/octet-stream",
        )
        form.add_field("type", "input")
        form.add_field("subfolder", subfolder)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/upload/image",
                    data=form,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as response:
                    response_payload = await response.json()
                    if response.status >= 400:
                        raise ProductionError(
                            ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                            f"ComfyUI rejected image upload with HTTP {response.status}",
                            response_payload if isinstance(response_payload, dict) else {},
                        )
        except ProductionError:
            raise
        except Exception as error:
            raise ProductionError(
                ProductionErrorCode.COMFY_CONNECTION_FAILED,
                str(error),
            ) from error
        if not isinstance(response_payload, dict):
            raise ProductionError(
                ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                "ComfyUI image upload returned an invalid response",
            )
        uploaded_filename = str(response_payload.get("name", ""))
        uploaded_subfolder = str(response_payload.get("subfolder", ""))
        upload_type = str(response_payload.get("type", "input"))
        _safe_relative_path(uploaded_filename)
        _safe_relative_path(uploaded_subfolder, allow_empty=True)
        if upload_type != "input":
            raise ProductionError(
                ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                f"Unexpected ComfyUI upload type: {upload_type}",
            )
        return ComfyImageReference(
            filename=uploaded_filename,
            subfolder=uploaded_subfolder,
            type=upload_type,
        )

    async def wait_for_completion(self, prompt_id: str) -> dict[str, Any]:
        import aiohttp

        start = time.monotonic()
        while time.monotonic() - start < self.timeout_seconds:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{self.base_url}/history/{prompt_id}",
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        payload = await response.json()
                        if not isinstance(payload, dict):
                            raise ProductionError(
                                ProductionErrorCode.COMFY_EXECUTION_FAILED,
                                f"ComfyUI history for {prompt_id} is not an object",
                            )
                        entry = payload.get(prompt_id)
                        if entry is not None:
                            if not isinstance(entry, dict):
                                raise ProductionError(
                                    ProductionErrorCode.COMFY_EXECUTION_FAILED,
                                    f"ComfyUI history entry for {prompt_id} is invalid",
                                )
                            status = entry.get("status")
                            if not isinstance(status, dict):
                                raise ProductionError(
                                    ProductionErrorCode.COMFY_EXECUTION_FAILED,
                                    f"ComfyUI history status for {prompt_id} is invalid",
                                )
                            status_str = status.get("status_str")
                            completed = status.get("completed")
                            if not isinstance(status_str, str) or not isinstance(completed, bool):
                                raise ProductionError(
                                    ProductionErrorCode.COMFY_EXECUTION_FAILED,
                                    f"ComfyUI history status for {prompt_id} is malformed",
                                    {"status": status},
                                )
                            if status_str == "error":
                                details = _execution_error_details(status)
                                message = details.get(
                                    "exception_message",
                                    f"ComfyUI job {prompt_id} failed",
                                )
                                if "out of memory" in message.lower():
                                    self.state = ComfyUIState.OOM
                                    code = ProductionErrorCode.COMFY_OOM
                                else:
                                    self.state = ComfyUIState.IDLE
                                    code = ProductionErrorCode.COMFY_EXECUTION_FAILED
                                raise ProductionError(code, message, details)
                            if status_str in {"cancelled", "canceled"}:
                                self.state = ComfyUIState.IDLE
                                raise ProductionError(
                                    ProductionErrorCode.COMFY_EXECUTION_FAILED,
                                    f"ComfyUI job {prompt_id} was {status_str}",
                                    {"status": status},
                                )
                            if completed:
                                self.state = ComfyUIState.IDLE
                                if status_str != "success":
                                    raise ProductionError(
                                        ProductionErrorCode.COMFY_EXECUTION_FAILED,
                                        f"ComfyUI job {prompt_id} ended with status {status_str}",
                                        {"status": status},
                                    )
                                outputs = entry.get("outputs", {})
                                if not isinstance(outputs, dict):
                                    raise ProductionError(
                                        ProductionErrorCode.COMFY_EXECUTION_FAILED,
                                        f"ComfyUI job {prompt_id} returned malformed outputs",
                                    )
                                if outputs:
                                    return outputs
                                raise ProductionError(
                                    ProductionErrorCode.COMFY_NO_OUTPUT,
                                    f"ComfyUI job {prompt_id} completed without media outputs",
                                    {"status": status},
                                )
                            if status_str == "success":
                                raise ProductionError(
                                    ProductionErrorCode.COMFY_EXECUTION_FAILED,
                                    f"ComfyUI job {prompt_id} reported success before completion",
                                    {"status": status},
                                )
            except ProductionError:
                raise
            except Exception as error:
                self._last_error = str(error)
            await asyncio.sleep(self.poll_interval)

        raise ProductionError(
            ProductionErrorCode.COMFY_TIMEOUT,
            f"ComfyUI job {prompt_id} did not complete within {self.timeout_seconds}s",
        )

    async def submit_and_wait(
        self,
        workflow: dict[str, Any],
        on_submitted: Callable[[str], Any] | None = None,
    ) -> ComfyCompletedWorkflow:
        """Submit a workflow and return its prompt id only after terminal history.

        ``on_submitted`` runs after ComfyUI accepts the prompt and before the
        first history poll.  It is the durable checkpoint boundary used by the
        formal novel-video worker to make a crash resumable without submitting
        a second prompt.
        """
        prompt_id = await self.submit_workflow(workflow)
        if on_submitted is not None:
            outcome = on_submitted(prompt_id)
            if inspect.isawaitable(outcome):
                await outcome
        try:
            outputs = await self.wait_for_completion(prompt_id)
        except ProductionError as error:
            # A history timeout follows an accepted `/prompt`; callers must
            # reconcile this exact id, never submit an untracked replacement.
            error.details = {**dict(error.details), "accepted_prompt_id": prompt_id}
            raise
        return ComfyCompletedWorkflow(prompt_id=prompt_id, outputs=outputs)

    async def generate_to_file(
        self,
        workflow: dict[str, Any],
        destination: str | Path,
    ) -> ComfyArtifact:
        path = Path(destination)
        completed = await self.submit_and_wait(workflow)
        artifact = self.first_artifact(completed.outputs)
        payload = await self.download_artifact(artifact)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        if path.stat().st_size == 0:
            raise ProductionError(
                ProductionErrorCode.COMFY_NO_OUTPUT,
                f"Downloaded artifact is empty: {path}",
            )
        return artifact

    @staticmethod
    def artifact_from_node(
        outputs: dict[str, Any],
        node_id: str,
        media_kinds: tuple[str, ...] = ("videos", "gifs"),
    ) -> ComfyArtifact:
        """Select downloadable media emitted by the specified terminal workflow node."""
        node_output = outputs.get(node_id)
        if isinstance(node_output, dict):
            for media_kind in media_kinds:
                items = node_output.get(media_kind, [])
                if not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, dict) and item.get("filename"):
                        return ComfyArtifact(
                            filename=str(item["filename"]),
                            subfolder=str(item.get("subfolder", "")),
                            type=str(item.get("type", "output")),
                            media_kind=media_kind,
                        )
        raise ProductionError(
            ProductionErrorCode.COMFY_NO_OUTPUT,
            f"ComfyUI history contains no video output from node {node_id}",
            {"node_id": node_id},
        )

    @staticmethod
    def first_artifact(outputs: dict[str, Any]) -> ComfyArtifact:
        media_keys = ("images", "videos", "gifs", "audio")
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            for media_kind in media_keys:
                items = node_output.get(media_kind, [])
                if not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, dict) and item.get("filename"):
                        return ComfyArtifact(
                            filename=str(item["filename"]),
                            subfolder=str(item.get("subfolder", "")),
                            type=str(item.get("type", "output")),
                            media_kind=media_kind,
                        )
        raise ProductionError(
            ProductionErrorCode.COMFY_NO_OUTPUT,
            "ComfyUI history contains no downloadable media artifact",
        )

    async def download_artifact(self, artifact: ComfyArtifact) -> bytes:
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/view",
                    params={
                        "filename": artifact.filename,
                        "subfolder": artifact.subfolder,
                        "type": artifact.type,
                    },
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as response:
                    if response.status != 200:
                        raise ProductionError(
                            ProductionErrorCode.COMFY_NO_OUTPUT,
                            f"Unable to download {artifact.filename}: HTTP {response.status}",
                        )
                    return await response.read()
        except ProductionError:
            raise
        except Exception as error:
            raise ProductionError(
                ProductionErrorCode.COMFY_CONNECTION_FAILED,
                str(error),
            ) from error

    async def cancel_job(self, prompt_id: str) -> CancelJobResult:
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/queue", timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        raise ProductionError(ProductionErrorCode.COMFY_CONNECTION_FAILED, f"Unable to inspect ComfyUI queue: HTTP {response.status}")
                    before = await response.json()
                running = _queue_prompt_ids(before, "queue_running")
                pending = _queue_prompt_ids(before, "queue_pending")
                if prompt_id in running:
                    # ComfyUI's public `/interrupt` endpoint is process-global,
                    # not prompt-scoped.  A running-slot handoff can occur
                    # immediately after any queue read, so no sequence of
                    # rechecks makes that endpoint safe for one target.  Only
                    # exact terminal history can resolve this request; while it
                    # is still running we deliberately leave it uncertain for
                    # later journal reconciliation.
                    state = await _cancel_history_state(session, self.base_url, prompt_id, polls=1)
                    return CancelJobResult(prompt_id, state, True)
                if prompt_id not in pending:
                    state = await _cancel_history_state(session, self.base_url, prompt_id, polls=1)
                    return CancelJobResult(prompt_id, state, False)
                async with session.post(
                    f"{self.base_url}/queue",
                    json={"delete": [prompt_id]},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status not in {200, 201}:
                        raise ProductionError(ProductionErrorCode.COMFY_CONNECTION_FAILED, f"ComfyUI queue delete failed: HTTP {response.status}")
                async with session.get(
                    f"{self.base_url}/queue", timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        raise ProductionError(ProductionErrorCode.COMFY_CONNECTION_FAILED, f"Unable to verify ComfyUI queue: HTTP {response.status}")
                    after = await response.json()
                remaining = _queue_prompt_ids(after, "queue_running") | _queue_prompt_ids(after, "queue_pending")
                state = "verified_cancelled" if prompt_id not in remaining else "uncertain"
                return CancelJobResult(prompt_id, state, False)
        except ProductionError:
            raise
        except Exception as error:
            raise ProductionError(ProductionErrorCode.COMFY_CONNECTION_FAILED, f"Unable to verify cancellation for {prompt_id}: {error}") from error

    async def free_memory(self) -> None:
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{self.base_url}/free",
                    json={"unload_models": True, "free_memory": True},
                    timeout=aiohttp.ClientTimeout(total=30),
                )
        except Exception:
            return


def _queue_prompt_ids(payload: Any, key: str) -> set[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
        raise ProductionError(ProductionErrorCode.COMFY_CONNECTION_FAILED, "ComfyUI queue response is malformed")
    found: set[str] = set()
    for item in payload[key]:
        if isinstance(item, list) and len(item) > 1 and isinstance(item[1], str):
            found.add(item[1])
    return found


def _queue_prompt_order(payload: Any, key: str) -> list[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
        raise ProductionError(ProductionErrorCode.COMFY_CONNECTION_FAILED, "ComfyUI queue response is malformed")
    return [
        item[1] for item in payload[key]
        if isinstance(item, list) and len(item) > 1 and isinstance(item[1], str)
    ]


async def _cancel_history_state(
    session: Any, base_url: str, prompt_id: str, *, polls: int = 5,
) -> str:
    """Require terminal history for an exact previously-running prompt."""
    import aiohttp

    for poll in range(polls):
        try:
            async with session.get(
                f"{base_url}/history/{prompt_id}", timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status != 200:
                    return "uncertain"
                payload = await response.json()
        except Exception:
            return "uncertain"
        entry = payload.get(prompt_id) if isinstance(payload, dict) else None
        status = entry.get("status") if isinstance(entry, dict) else None
        if isinstance(status, dict):
            status_str = status.get("status_str")
            completed = status.get("completed")
            if status_str in {"cancelled", "canceled", "error"} and isinstance(completed, bool):
                return "verified_cancelled"
            if completed is True and status_str == "success":
                return "completed"
        if poll < polls - 1:
            await asyncio.sleep(0.05)
    return "uncertain"


def _execution_error_details(status: dict[str, Any]) -> dict[str, Any]:
    messages = status.get("messages", [])
    for message in reversed(messages):
        if (
            isinstance(message, list)
            and len(message) == 2
            and message[0] == "execution_error"
            and isinstance(message[1], dict)
        ):
            return message[1]
    return {"status": status}


def _safe_relative_path(value: str, allow_empty: bool = False) -> None:
    if not value and allow_empty:
        return
    normalized = value.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if (
        not value
        or candidate.is_absolute()
        or normalized != value
        or any(part in ("", ".", "..") for part in candidate.parts)
    ):
        raise ProductionError(
            ProductionErrorCode.COMFY_WORKFLOW_INVALID,
            f"Unsafe ComfyUI image reference: {value!r}",
        )
