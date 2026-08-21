"""Permissioned, recoverable routing for formal MiniMax H3 novel-video segments."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from backend.production.comfy_adapter import ProductionError, ProductionErrorCode

logger = logging.getLogger(__name__)

OOM_AREA_FACTOR = 0.75
OOM_ALIGNMENT_MULTIPLE = 32
OOM_MIN_TARGET_RETENTION = 0.90
OOM_MAX_ASPECT_ERROR = 0.02
OOM_MIN_PIXELS = 300_000
# Only terminal provider-runtime availability/execution codes may cross the approved engine boundary.
# Validation, preflight, workflow/schema, model/configuration, and unknown failures stay on H3.
FALLBACKABLE_H3_ERROR_CODES = frozenset({
    ProductionErrorCode.COMFY_CONNECTION_FAILED,
    ProductionErrorCode.COMFY_TIMEOUT,
    ProductionErrorCode.COMFY_EXECUTION_FAILED,
})
BlockedCallback = Callable[[dict[str, Any]], Any]


@dataclass
class NovelVideoRouter:
    """Route an approved segment to H3 first, with only explicit local Wan fallback."""

    h3: Any
    wan: Any | None
    allow_wan_fallback: bool = False
    on_blocked: BlockedCallback | None = None

    async def generate(self, request: Any) -> Any:
        """Generate once, retry transport once, and perform the single permitted OOM downgrade."""
        try:
            return await self.h3.generate(request)
        except Exception as error:
            accepted_prompt = _accepted_prompt_id(error)
            if accepted_prompt and hasattr(self.h3, "resume"):
                # An accepted request, including an OOM report, is tracked work
                # and cannot be replaced by an untracked downgraded prompt.
                return await self.resume(request, accepted_prompt)
            if _is_transport_error(error):
                try:
                    accepted_prompt = _accepted_prompt_id(error)
                    if accepted_prompt and hasattr(self.h3, "resume"):
                        return await self.h3.resume(request, accepted_prompt)
                    return await self.h3.generate(request)
                except Exception as retry_error:
                    retry_prompt = _accepted_prompt_id(retry_error)
                    if retry_prompt and hasattr(self.h3, "resume"):
                        return await self.resume(request, retry_prompt)
                    if _is_oom(retry_error):
                        return await self._retry_oom_once(request, retry_error)
                    return await self._fallback_or_raise(request, retry_error)
            if _is_oom(error):
                return await self._retry_oom_once(request, error)
            return await self._fallback_or_raise(request, error)

    async def resume(self, request: Any, prompt_id: str, checkpoint: dict[str, Any] | None = None) -> Any:
        """Reconcile a durable H3 prompt checkpoint without opening a new provider route."""
        resume = getattr(self.h3, "resume", None)
        if resume is None:
            raise ProductionError(
                ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                "Configured H3 provider cannot resume a persisted prompt",
            )
        try:
            return await resume(request, prompt_id, checkpoint)
        except TypeError:
            # Compatibility for non-production test/legacy providers; the
            # production H3 provider validates the checkpoint argument above.
            return await resume(request, prompt_id)

    async def _retry_oom_once(self, request: Any, first_error: Exception) -> Any:
        geometry = _geometry(request)
        downgraded = _downgrade_request(request, geometry)
        if geometry["actual_area"] < OOM_MIN_PIXELS:
            await self._record_blocked(
                request, "oom_downgrade_below_minimum", first_error, geometry
            )
            _attach_routing_evidence(first_error, geometry)
            raise first_error
        if not geometry["valid"] or downgraded is None:
            await self._record_blocked(
                request, "oom_geometry_outside_tolerance", first_error, geometry
            )
            _attach_routing_evidence(first_error, geometry)
            raise first_error
        try:
            result = await self.h3.generate(downgraded)
        except Exception as error:
            await self._record_blocked(request, "oom_downgrade_failed", error, geometry)
            _attach_routing_evidence(error, geometry)
            raise
        return _with_size_evidence(result, request, downgraded, geometry)

    async def _fallback_or_raise(self, request: Any, error: Exception) -> Any:
        if self.allow_wan_fallback and self.wan is not None and _is_fallbackable_h3_error(error):
            try:
                return await self.wan.generate(_wan_request(request))
            except Exception as fallback_error:
                _attach_routing_evidence(fallback_error, _geometry(request))
                raise
        _attach_routing_evidence(error, _geometry(request))
        raise error

    async def _record_blocked(
        self,
        request: Any,
        reason: str,
        error: Exception,
        geometry: dict[str, Any],
    ) -> None:
        if self.on_blocked is None:
            return
        evidence = {
            "reason": reason,
            "error_code": _error_code(error),
            "original_size": geometry["original_size"],
            "downgraded_size": geometry["downgraded_size"],
            "geometry": geometry,
        }
        try:
            outcome = self.on_blocked(evidence)
            if inspect.isawaitable(outcome):
                await outcome
        except Exception:
            logger.exception("Optional novel-video blocked callback failed")


def _is_transport_error(error: Exception) -> bool:
    return isinstance(error, (ConnectionError, TimeoutError, asyncio.TimeoutError)) or (
        isinstance(error, ProductionError)
        and error.code in {
            ProductionErrorCode.COMFY_CONNECTION_FAILED,
            ProductionErrorCode.COMFY_TIMEOUT,
        }
    )


def _is_oom(error: Exception) -> bool:
    return isinstance(error, ProductionError) and error.code is ProductionErrorCode.COMFY_OOM


def _is_fallbackable_h3_error(error: Exception) -> bool:
    """Allow only explicitly classified H3 provider-runtime failures to enter Wan."""
    return isinstance(error, ProductionError) and error.code in FALLBACKABLE_H3_ERROR_CODES


def _accepted_prompt_id(error: Exception) -> str | None:
    value = getattr(error, "details", {}).get("accepted_prompt_id") if isinstance(error, ProductionError) else None
    return value if isinstance(value, str) and value else None


def _downgrade_request(request: Any, geometry: dict[str, Any] | None = None) -> Any | None:
    reduced_size = (geometry or _geometry(request))["downgraded_size"]
    reduced_width = reduced_size["width"]
    reduced_height = reduced_size["height"]
    if reduced_width * reduced_height < OOM_MIN_PIXELS:
        return None
    package = getattr(request, "package", None)
    if package is not None and hasattr(package, "width") and hasattr(package, "height"):
        resized_package = package.model_copy(
            update={"width": reduced_width, "height": reduced_height}
        )
        return replace(request, package=resized_package)
    return replace(request, width=reduced_width, height=reduced_height)


def _geometry(request: Any) -> dict[str, Any]:
    """Choose an aligned, never-oversize H3 OOM recovery geometry with explicit evidence."""
    width, height = _dimensions(request)
    scale = OOM_AREA_FACTOR ** 0.5
    target_area = width * height * OOM_AREA_FACTOR
    max_width = max(OOM_ALIGNMENT_MULTIPLE, int(width * scale) // OOM_ALIGNMENT_MULTIPLE * OOM_ALIGNMENT_MULTIPLE)
    max_height = max(OOM_ALIGNMENT_MULTIPLE, int(height * scale) // OOM_ALIGNMENT_MULTIPLE * OOM_ALIGNMENT_MULTIPLE)
    original_ratio = width / height
    candidates = [
        {"width": candidate_width, "height": candidate_height}
        for candidate_width in range(OOM_ALIGNMENT_MULTIPLE, max_width + 1, OOM_ALIGNMENT_MULTIPLE)
        for candidate_height in range(OOM_ALIGNMENT_MULTIPLE, max_height + 1, OOM_ALIGNMENT_MULTIPLE)
        if candidate_width * candidate_height <= target_area
    ]
    reduced = (
        min(
            candidates,
            key=lambda size: (
                target_area - size["width"] * size["height"],
                abs(size["width"] / size["height"] - original_ratio) / original_ratio,
            ),
        )
        if candidates else {"width": max_width, "height": max_height}
    )
    actual_area = reduced["width"] * reduced["height"]
    actual_ratio = reduced["width"] / reduced["height"]
    target_retention = actual_area / target_area if target_area else 0.0
    aspect_error = abs(actual_ratio - original_ratio) / original_ratio
    valid = (
        actual_area <= target_area
        and target_retention >= OOM_MIN_TARGET_RETENTION
        and aspect_error <= OOM_MAX_ASPECT_ERROR
        and actual_area >= OOM_MIN_PIXELS
    )
    return {
        "original_size": {"width": width, "height": height},
        "downgraded_size": reduced,
        "target_area": target_area,
        "actual_area": actual_area,
        "actual_reduction": 1 - actual_area / (width * height),
        "target_retention": target_retention,
        "aspect_error": aspect_error,
        "alignment_multiple": OOM_ALIGNMENT_MULTIPLE,
        "bounds": {
            "area_factor": OOM_AREA_FACTOR,
            "min_target_retention": OOM_MIN_TARGET_RETENTION,
            "max_aspect_error": OOM_MAX_ASPECT_ERROR,
            "min_pixels": OOM_MIN_PIXELS,
        },
        "valid": valid,
    }


def _with_size_evidence(result: Any, original: Any, downgraded: Any, geometry: dict[str, Any]) -> Any:
    metadata = dict(result.metadata)
    metadata["routing"] = {
        "original_size": _size(original),
        "downgraded_size": _size(downgraded),
        "geometry": geometry,
        "reason": "oom_first_retry",
    }
    return replace(result, metadata=metadata)


def _size(request: Any) -> dict[str, int]:
    width, height = _dimensions(request)
    return {"width": width, "height": height}


def _dimensions(request: Any) -> tuple[int, int]:
    package = getattr(request, "package", None)
    source = package if package is not None and hasattr(package, "width") else request
    return int(source.width), int(source.height)


def _error_code(error: Exception) -> str:
    if isinstance(error, ProductionError):
        return error.code.value
    return type(error).__name__


def _attach_routing_evidence(error: Exception, geometry: dict[str, Any]) -> None:
    """Keep a terminal router failure self-describing for the atomic formal-worker record."""
    if isinstance(error, ProductionError):
        details = dict(error.details)
        details["routing"] = geometry
        error.details = details


def _wan_request(request: Any) -> Any:
    """Translate the formal H3 contract to Wan's native VideoRequest boundary."""
    package = getattr(request, "package", None)
    if package is None:
        return request
    pictures = tuple(getattr(request, "picture_paths", ()))
    if not pictures:
        raise ProductionError(
            ProductionErrorCode.MEDIA_VALIDATION_FAILED,
            "Wan fallback requires the authoritative first H3 picture path",
        )
    from backend.production.providers import VideoRequest

    return VideoRequest(
        image_path=Path(pictures[0]), prompt=package.prompt_text, negative_prompt=package.negative_prompt,
        seed=package.effective_seed, width=package.width, height=package.height,
        frames=package.legal_frame_count, fps=package.fps, output_path=request.output_video,
        ai_video=True,
    )
