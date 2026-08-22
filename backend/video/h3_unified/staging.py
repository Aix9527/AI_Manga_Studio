from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from .reference_bundle import H3ReferenceBundle
from .ui_state import H3UnifiedRequest


async def stage_h3_unified_request(
    request: H3UnifiedRequest,
    adapter: Any,
    *,
    subfolder: str = "h3_unified",
) -> H3UnifiedRequest:
    """Upload local H3 media once per source and return an immutable staged copy."""

    cache: dict[tuple[str, str], str] = {}

    async def staged_reference(kind: str, path: str) -> str:
        key = (kind, _source_key(path))
        if key in cache:
            return cache[key]
        uploader = getattr(adapter, f"upload_{kind}")
        reference = await uploader(path, subfolder=subfolder)
        cache[key] = reference.reference
        return reference.reference

    staged_images: dict[str, str] = {}
    for field, path in request.references.image_references():
        staged_images[field] = await staged_reference("image", path)

    staged_videos = [
        await staged_reference("video", path)
        for path in request.references.videos
    ]
    staged_audios = [
        await staged_reference("audio", path)
        for path in request.references.audios
    ]

    first_frame = request.first_frame
    if first_frame:
        first_frame = await staged_reference("image", first_frame)

    last_frame = request.last_frame
    if last_frame:
        last_frame = await staged_reference("image", last_frame)

    staged_bundle = H3ReferenceBundle(
        **staged_images,
        videos=tuple(staged_videos),
        audios=tuple(staged_audios),
    )
    return replace(
        request,
        references=staged_bundle,
        first_frame=first_frame,
        last_frame=last_frame,
    )


def _source_key(path: str) -> str:
    """Use a stable local-path identity without requiring the file to exist twice."""

    return str(Path(path).expanduser().resolve(strict=False))
