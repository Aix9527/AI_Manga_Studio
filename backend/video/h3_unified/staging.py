from __future__ import annotations

from dataclasses import replace
from typing import Any

from .reference_bundle import H3ReferenceBundle
from .ui_state import H3UnifiedRequest


async def stage_h3_unified_request(
    request: H3UnifiedRequest,
    adapter: Any,
    *,
    subfolder: str = "h3_unified",
) -> H3UnifiedRequest:
    """Upload all local H3 reference media and return an immutable staged copy."""

    staged_images: dict[str, str] = {}
    for field, path in request.references.image_references():
        reference = await adapter.upload_image(path, subfolder=subfolder)
        staged_images[field] = reference.reference

    staged_videos = []
    for path in request.references.videos:
        reference = await adapter.upload_video(path, subfolder=subfolder)
        staged_videos.append(reference.reference)

    staged_audios = []
    for path in request.references.audios:
        reference = await adapter.upload_audio(path, subfolder=subfolder)
        staged_audios.append(reference.reference)

    first_frame = request.first_frame
    if first_frame:
        first_reference = await adapter.upload_image(first_frame, subfolder=subfolder)
        first_frame = first_reference.reference

    last_frame = request.last_frame
    if last_frame:
        last_reference = await adapter.upload_image(last_frame, subfolder=subfolder)
        last_frame = last_reference.reference

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
