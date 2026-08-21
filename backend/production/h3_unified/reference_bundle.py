from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .contracts import (
    H3AudioRole,
    H3ImageRole,
    H3ReferenceBundle,
    H3ReferenceItem,
    H3VideoRole,
)


def _canonical_path(value: str | Path) -> str:
    return str(value).replace("\\", "/").casefold()


def _ordered_items(
    kind: str,
    roles: type[H3ImageRole] | type[H3VideoRole] | type[H3AudioRole],
    values: Mapping | None,
) -> tuple[H3ReferenceItem, ...]:
    values = values or {}
    seen: set[str] = set()
    items: list[H3ReferenceItem] = []
    for role in roles:
        value = values.get(role)
        if value is None or str(value) == "":
            continue
        path = str(value)
        canonical = _canonical_path(path)
        if canonical in seen:
            continue
        seen.add(canonical)
        items.append(H3ReferenceItem(kind=kind, role=role, path=path))
    return tuple(items)


def build_reference_bundle(
    *,
    image_roles: Mapping[H3ImageRole, str | Path] | None = None,
    videos: Mapping[H3VideoRole, str | Path] | None = None,
    audios: Mapping[H3AudioRole, str | Path] | None = None,
) -> H3ReferenceBundle:
    """Pack semantic H3 references in deterministic production priority order."""
    return H3ReferenceBundle(
        images=_ordered_items("image", H3ImageRole, image_roles),
        videos=_ordered_items("video", H3VideoRole, videos),
        audios=_ordered_items("audio", H3AudioRole, audios),
    )
