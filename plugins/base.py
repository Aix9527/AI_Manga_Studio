"""
AI Manga Studio Pro V1.0 — Plugin Base Classes

Abstract base classes defining the standard interface for each
plugin type. Every plugin must implement the corresponding ABC.

Design principle: Each plugin is a self-contained module. When
a new model is released (e.g., Wan3), only replace plugins/wan/
— nothing else in the system changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ImagePlugin(ABC):
    """Generate a single image for a shot."""

    @abstractmethod
    def generate(self, shot: Any) -> str:
        """Generate image from shot data.

        Args:
            shot: UnifiedShot object with all shot metadata.

        Returns:
            Absolute path to generated image file.
        """
        ...

    @abstractmethod
    def check_prerequisites(self) -> bool:
        """Check if this plugin's dependencies are ready.

        Returns:
            True if all models/dependencies are available.
        """
        ...


class VideoPlugin(ABC):
    """Generate a video clip from an image (I2V)."""

    @abstractmethod
    def generate(self, shot: Any, image_path: str) -> str:
        """Generate video from source image.

        Args:
            shot: UnifiedShot object with motion/duration metadata.
            image_path: Path to source image.

        Returns:
            Absolute path to generated video file.
        """
        ...

    @abstractmethod
    def check_prerequisites(self) -> bool:
        """Check if this plugin's dependencies are ready."""
        ...


class TTSPlugin(ABC):
    """Generate speech audio from text."""

    @abstractmethod
    def generate(
        self,
        text: str,
        voice: str = "",
        output_path: str = "",
    ) -> str:
        """Synthesize speech from text.

        Args:
            text: Dialogue text to speak.
            voice: Voice identifier (plugin-specific).
            output_path: Target audio file path (.wav/.mp3).

        Returns:
            Absolute path to generated audio file.
        """
        ...


class SubtitlePlugin(ABC):
    """Generate subtitle files (SRT/ASS)."""

    @abstractmethod
    def generate(
        self,
        shots: List[Any],
        timing: Optional[Dict[str, float]] = None,
        output_path: str = "",
        template: str = "basic",
    ) -> str:
        """Generate subtitle file from shot data.

        Args:
            shots: List of UnifiedShot objects.
            timing: Optional timing overrides.
            output_path: Target SRT file path.
            template: Subtitle style template name.

        Returns:
            Absolute path to generated subtitle file.
        """
        ...


class MusicPlugin(ABC):
    """Generate or select background music."""

    @abstractmethod
    def generate(
        self,
        scene_context: Dict[str, Any],
        duration: float = 0.0,
        output_path: str = "",
    ) -> str:
        """Generate/fetch background music.

        Args:
            scene_context: Scene mood/tempo/theme info.
            duration: Target duration in seconds.
            output_path: Target audio file path.

        Returns:
            Absolute path to music file.
        """
        ...


class QualityPlugin(ABC):
    """Enhance media quality (upscale, denoise, etc.)."""

    @abstractmethod
    def enhance(
        self,
        input_path: str,
        output_path: str = "",
        params: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Enhance image/video quality.

        Args:
            input_path: Source media file.
            output_path: Target output path.
            params: Enhancement parameters.

        Returns:
            Absolute path to enhanced file.
        """
        ...
