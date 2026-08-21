from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class MediaArtifact:
    path: Path
    kind: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    negative_prompt: str
    seed: int
    width: int
    height: int
    output_path: Path
    reference_image: str = ""          # Path to character reference image for IP-Adapter
    ipadapter_weight: float = 0.85     # IP-Adapter influence strength (0.0-1.0)


@dataclass(frozen=True)
class VideoRequest:
    image_path: Path
    prompt: str
    negative_prompt: str
    seed: int
    width: int
    height: int
    frames: int
    fps: int
    output_path: Path
    motion_bucket_id: int = 127        # Wan2.2: 0-255, higher = more motion
    denoise_strength: float = 1.0       # Wan2.2: 0-1, how much to change the input image
    ai_video: bool = False              # Use AI video generation (Wan2.2) vs Ken Burns
    end_frame_path: str = ""            # FLF2V: last frame for first-last frame interpolation
    engine: str = ""                    # GPT Round-4: wan22_native / minimax_h3 (双引擎调度)


class ImageProvider(Protocol):
    async def generate(self, request: ImageRequest) -> MediaArtifact:
        raise NotImplementedError


class VideoProvider(Protocol):
    async def generate(self, request: VideoRequest) -> MediaArtifact:
        raise NotImplementedError
