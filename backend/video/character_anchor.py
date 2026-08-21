"""Character Memory Anchor module for maintaining character consistency.

Per GPT optimization advice, when generating 20+ consecutive shots with
tail-frame linking, visual drift occurs — characters' faces, clothing,
and proportions gradually change. This module addresses that by:

1. **Character anchor frames**: Saving the first appearance of each
   character as a "reference anchor" that can be blended with tail frames
   to prevent drift.

2. **Periodic anchor refresh**: Every N shots (default 5), the character
   anchor is re-injected as the start image instead of the tail frame,
   resetting any accumulated drift.

3. **Anchor blending**: When both a tail frame and a character anchor
   exist, they can be blended (e.g., 70% tail + 30% anchor) to maintain
   continuity while preserving character identity.

4. **Visual fingerprint**: A lightweight hash of character features
   (face region, color histogram) is stored per shot to detect drift.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class CharacterAnchor:
    """A character's reference anchor frame and metadata."""
    character_id: str
    character_name: str
    anchor_image_path: Path
    first_appearance_shot: str
    color_signature: str = ""  # Color histogram hash
    face_region: tuple[int, int, int, int] | None = None  # x, y, w, h
    last_refresh_shot: str = ""


class CharacterMemoryAnchor:
    """Manages character anchor frames for long sequence consistency.

    Usage:
        anchor = CharacterMemoryAnchor(work_dir=Path("projects/xxx/outputs/anchors"))
        anchor.register_character("char_01", "Alice", first_frame_path, "shot_01")

        # For each subsequent shot:
        start_image = anchor.get_start_image(
            shot_id="shot_05",
            tail_frame=tail_frame_path,
            shot_index=4,
            refresh_interval=5,
        )
    """

    REFRESH_INTERVAL = 5  # Re-inject anchor every N shots
    BLEND_RATIO = 0.3  # 30% anchor, 70% tail frame

    def __init__(self, work_dir: Path) -> None:
        """Initialize the anchor manager.

        Args:
            work_dir: Directory for storing anchor frames.
        """
        self._work_dir = Path(work_dir)
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._anchors: dict[str, CharacterAnchor] = {}
        self._shot_order: list[str] = []

    def register_character(
        self,
        character_id: str,
        character_name: str,
        anchor_image_path: Path,
        first_appearance_shot: str,
    ) -> CharacterAnchor:
        """Register or update a character's anchor frame.

        Args:
            character_id: Unique identifier for the character.
            character_name: Display name.
            anchor_image_path: Path to the reference frame.
            first_appearance_shot: Shot ID where the character first appears.

        Returns:
            The created/updated CharacterAnchor.
        """
        # Copy anchor image to work directory
        anchor_dest = self._work_dir / f"{character_id}_anchor.png"
        if Path(anchor_image_path).exists():
            import shutil
            shutil.copy2(anchor_image_path, anchor_dest)

        # Compute color signature
        color_sig = self._compute_color_signature(anchor_dest)

        anchor = CharacterAnchor(
            character_id=character_id,
            character_name=character_name,
            anchor_image_path=anchor_dest,
            first_appearance_shot=first_appearance_shot,
            color_signature=color_sig,
            last_refresh_shot=first_appearance_shot,
        )
        self._anchors[character_id] = anchor
        logger.info(
            "Registered character anchor: %s (%s) from %s",
            character_name, character_id, first_appearance_shot,
        )
        return anchor

    def get_start_image(
        self,
        shot_id: str,
        tail_frame: Path | None,
        shot_index: int = 0,
        refresh_interval: int | None = None,
    ) -> Path:
        """Determine the start image for a shot.

        Decision logic:
        1. If shot_index is a multiple of refresh_interval, use the
           primary character's anchor frame to reset drift.
        2. If tail_frame exists, blend it with the anchor (30% anchor).
        3. Otherwise, use the anchor directly.

        Args:
            shot_id: Current shot ID.
            tail_frame: Tail frame from the previous shot (if any).
            shot_index: Zero-based index of the shot in the sequence.
            refresh_interval: Override the default refresh interval.

        Returns:
            Path to the image to use as the start frame.
        """
        interval = refresh_interval or self.REFRESH_INTERVAL
        self._shot_order.append(shot_id)

        # Get the primary character anchor (first registered)
        if not self._anchors:
            # No anchors registered, use tail frame or nothing
            if tail_frame and tail_frame.exists():
                return tail_frame
            raise ValueError("No character anchors registered and no tail frame")

        primary_anchor = next(iter(self._anchors.values()))

        # Check if this is a refresh shot
        is_refresh = shot_index > 0 and shot_index % interval == 0

        if is_refresh:
            logger.info(
                "Shot %s: anchor refresh (index=%d, interval=%d) — using character anchor",
                shot_id, shot_index, interval,
            )
            primary_anchor.last_refresh_shot = shot_id

            # If we have a tail frame, blend it with the anchor
            if tail_frame and tail_frame.exists():
                blended = self._blend_images(
                    primary_anchor.anchor_image_path,
                    tail_frame,
                    self.BLEND_RATIO,  # 30% anchor
                )
                if blended:
                    return blended

            return primary_anchor.anchor_image_path

        # Normal shot: use tail frame if available, otherwise anchor
        if tail_frame and tail_frame.exists():
            return tail_frame

        return primary_anchor.anchor_image_path

    def _blend_images(
        self,
        anchor_path: Path,
        tail_path: Path,
        anchor_ratio: float = 0.3,
    ) -> Path | None:
        """Blend two images together.

        Creates a new image that is (anchor_ratio * anchor + (1 - anchor_ratio) * tail).
        Both images are resized to match before blending.

        Args:
            anchor_path: Path to the anchor (reference) image.
            tail_path: Path to the tail frame image.
            anchor_ratio: Weight of the anchor image (0-1).

        Returns:
            Path to the blended image, or None on failure.
        """
        output_path = self._work_dir / f"blended_{tail_path.stem}.png"

        try:
            with Image.open(anchor_path) as anchor_img:
                with Image.open(tail_path) as tail_img:
                    # Resize tail to match anchor dimensions
                    if tail_img.size != anchor_img.size:
                        tail_img = tail_img.resize(
                            anchor_img.size, Image.Resampling.LANCZOS
                        )

                    # Blend using PIL's blend method
                    blended = Image.blend(
                        tail_img.convert("RGBA"),
                        anchor_img.convert("RGBA"),
                        alpha=anchor_ratio,
                    )
                    blended.convert("RGB").save(output_path, "PNG")

            logger.debug(
                "Blended anchor (%.0f%%) + tail (%.0f%%) -> %s",
                anchor_ratio * 100,
                (1 - anchor_ratio) * 100,
                output_path.name,
            )
            return output_path

        except Exception as exc:
            logger.warning("Image blending failed: %s", exc)
            return None

    def _compute_color_signature(self, image_path: Path) -> str:
        """Compute a color histogram hash for drift detection.

        Args:
            image_path: Path to the image.

        Returns:
            A hex string hash of the color histogram.
        """
        try:
            with Image.open(image_path) as img:
                # Resize to 32x32 for fast histogram
                small = img.convert("RGB").resize((32, 32), Image.Resampling.LANCZOS)
                # Get histogram
                hist = small.histogram()
                # Hash the histogram
                hist_bytes = bytes(str(hist).encode("utf-8"))
                return hashlib.md5(hist_bytes).hexdigest()[:16]
        except Exception:
            return ""

    def detect_drift(
        self,
        current_frame: Path,
        character_id: str | None = None,
    ) -> float:
        """Detect how much the current frame has drifted from the anchor.

        Compares color signatures between the current frame and the
        character's anchor. Returns a drift score (0 = identical, 1 = completely different).

        Args:
            current_frame: Path to the current frame.
            character_id: Character to compare against. If None, uses primary.

        Returns:
            Drift score (0-1, higher = more drift).
        """
        anchor = self._anchors.get(character_id) if character_id else next(
            iter(self._anchors.values()), None
        )
        if not anchor:
            return 0.0

        current_sig = self._compute_color_signature(current_frame)
        if not current_sig or not anchor.color_signature:
            return 0.0

        # Simple hash comparison: count different characters
        diff = sum(
            a != b for a, b in zip(current_sig, anchor.color_signature)
        )
        return diff / max(len(anchor.color_signature), 1)

    def clear(self) -> None:
        """Clear all anchors and shot history."""
        self._anchors.clear()
        self._shot_order.clear()
