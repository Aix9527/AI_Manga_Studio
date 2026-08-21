from __future__ import annotations

import re

from .contracts import H3SegmentSpec

_DURATION_MARKER = re.compile(r"&\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*&")
_ANY_MARKER = re.compile(r"&[^&]*&")


def align_h3_frames(duration_seconds: float, fps: int = 24) -> int:
    requested = max(5, round(float(duration_seconds) * int(fps)))
    return requested + (5 - requested % 17) % 17


def parse_segment_script(script: str, base_seed: int, fps: int = 24) -> tuple[H3SegmentSpec, ...]:
    chunks = str(script).split("===")
    segments: list[H3SegmentSpec] = []
    for index, raw_chunk in enumerate(chunks):
        chunk = raw_chunk.strip()
        human_index = index + 1
        if not chunk:
            raise ValueError(f"segment {human_index} is empty")
        match = _DURATION_MARKER.search(chunk)
        if _ANY_MARKER.search(chunk) is not None and match is None:
            raise ValueError(f"segment {human_index} has invalid duration marker")
        duration = float(match.group(1)) if match else 5.0
        duration = max(5.0, min(15.0, duration))
        prompt = _DURATION_MARKER.sub("", chunk).strip()
        if not prompt:
            raise ValueError(f"segment {human_index} is empty")
        segments.append(H3SegmentSpec(
            index=index,
            prompt=prompt,
            duration_seconds=duration,
            frames=align_h3_frames(duration, fps),
            fps=int(fps),
            seed=int(base_seed) + index,
            continuity_from_index=index - 1 if index else None,
        ))
    return tuple(segments)
