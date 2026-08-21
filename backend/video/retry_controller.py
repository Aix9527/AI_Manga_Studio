"""Retry Controller module for automatic failure recovery.

Per GPT optimization advice (v2), this module implements an intelligent
retry system that:

1. **Analyzes quality failures**: When the Quality Gate detects mosaic,
   flickering, or other issues, the Retry Controller determines the root
   cause and adjusts generation parameters accordingly.

2. **Parameter adjustment**: Based on the type of failure:
   - Mosaic: Reduce denoise, increase steps, lower CFG
   - Flickering: Lower CFG, increase temporal consistency weight
   - Too dark: Add brightness keywords to prompt
   - Too bright: Reduce exposure in prompt
   - Low temporal consistency: Increase steps, reduce motion

3. **Exponential backoff**: Retries use increasing parameter adjustments
   with each attempt to escape local minima.

4. **Max retry limit**: After 3 failed attempts, the controller gives up
   and returns the best available result.

5. **Quality history**: Tracks quality scores across retries to detect
   improvement or stagnation.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RetryAttempt:
    """Record of a single retry attempt."""
    attempt_number: int
    adjustments: list[str] = field(default_factory=list)
    quality_score: float = 0.0
    passed: bool = False
    failure_reasons: list[str] = field(default_factory=list)


@dataclass
class RetryResult:
    """Result of a retry operation."""
    shot_id: str
    status: str = "pending"  # pending, success, failed, max_retries
    total_attempts: int = 0
    attempts: list[RetryAttempt] = field(default_factory=list)
    final_quality_score: float = 0.0
    message: str = ""
    video_path: str = ""
    adjustments_applied: list[str] = field(default_factory=list)


class RetryController:
    """Manages automatic retry logic for failed video generations.

    Usage:
        controller = RetryController()
        result = await controller.retry_failed_shot(
            project_id="proj_001",
            shot_id="shot_03",
            quality_report=quality_report,
            max_retries=3,
        )
    """

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self._retry_history: dict[str, int] = {}
        self._quality_history: dict[str, list[float]] = {}

    def _adjust_parameters_for_mosaic(
        self,
        shot_data: dict[str, Any],
        retry_num: int,
    ) -> list[str]:
        """Adjust parameters to fix mosaic/noise issues.

        Reduces denoise (less change from original = less noise injection),
        increases steps (better convergence), and lowers CFG (less contrast
        amplification that causes blocky artifacts).
        """
        adjustments: list[str] = []

        # Reduce denoise progressively (0.55 -> 0.45 -> 0.35 -> 0.30)
        current_denoise = shot_data.get("denoise", 0.55)
        new_denoise = max(0.30, current_denoise - 0.10 * retry_num)
        shot_data["denoise"] = new_denoise
        adjustments.append(f"denoise: {current_denoise:.2f} -> {new_denoise:.2f}")

        # Increase steps for better convergence
        current_steps = shot_data.get("steps", 30)
        new_steps = min(45, current_steps + 5 * retry_num)
        shot_data["steps"] = new_steps
        adjustments.append(f"steps: {current_steps} -> {new_steps}")

        # Lower CFG to reduce blocky artifacts
        current_cfg = shot_data.get("cfg", 3.0)
        new_cfg = max(2.0, current_cfg - 0.3 * retry_num)
        shot_data["cfg"] = new_cfg
        adjustments.append(f"cfg: {current_cfg:.1f} -> {new_cfg:.1f}")

        return adjustments

    def _adjust_parameters_for_flickering(
        self,
        shot_data: dict[str, Any],
        retry_num: int,
    ) -> list[str]:
        """Adjust parameters to fix temporal flickering."""
        adjustments: list[str] = []

        # Lower CFG for temporal stability
        current_cfg = shot_data.get("cfg", 3.0)
        new_cfg = max(2.0, current_cfg - 0.2 * retry_num)
        shot_data["cfg"] = new_cfg
        adjustments.append(f"cfg: {current_cfg:.1f} -> {new_cfg:.1f} (temporal stability)")

        # Reduce motion intensity
        current_motion = shot_data.get("motion_bucket_id", 127)
        new_motion = max(80, current_motion - 15 * retry_num)
        shot_data["motion_bucket_id"] = new_motion
        adjustments.append(f"motion: {current_motion} -> {new_motion}")

        return adjustments

    def _adjust_parameters_for_dark(
        self,
        shot_data: dict[str, Any],
        retry_num: int,
    ) -> list[str]:
        """Adjust parameters to fix too-dark videos."""
        adjustments: list[str] = []

        current_prompt = shot_data.get("positive_prompt", "")
        brightness_keywords = "well-lit, bright lighting, clear visibility"

        if "well-lit" not in current_prompt.lower():
            shot_data["positive_prompt"] = f"{current_prompt}, {brightness_keywords}"
            adjustments.append(f"prompt += '{brightness_keywords}'")

        # Increase denoise slightly to allow more brightness variation
        current_denoise = shot_data.get("denoise", 0.55)
        new_denoise = min(0.65, current_denoise + 0.05 * retry_num)
        shot_data["denoise"] = new_denoise
        adjustments.append(f"denoise: {current_denoise:.2f} -> {new_denoise:.2f} (allow brightness)")

        return adjustments

    def _adjust_parameters_for_bright(
        self,
        shot_data: dict[str, Any],
        retry_num: int,
    ) -> list[str]:
        """Adjust parameters to fix too-bright videos."""
        adjustments: list[str] = []

        current_prompt = shot_data.get("positive_prompt", "")
        darkness_keywords = "dramatic lighting, controlled exposure, cinematic shadows"

        if "controlled exposure" not in current_prompt.lower():
            shot_data["positive_prompt"] = f"{current_prompt}, {darkness_keywords}"
            adjustments.append(f"prompt += '{darkness_keywords}'")

        return adjustments

    def _adjust_parameters_for_low_consistency(
        self,
        shot_data: dict[str, Any],
        retry_num: int,
    ) -> list[str]:
        """Adjust parameters to fix low temporal consistency."""
        adjustments: list[str] = []

        # Increase steps for better temporal coherence
        current_steps = shot_data.get("steps", 30)
        new_steps = min(45, current_steps + 5 * retry_num)
        shot_data["steps"] = new_steps
        adjustments.append(f"steps: {current_steps} -> {new_steps} (temporal coherence)")

        # Reduce denoise for less frame-to-frame variation
        current_denoise = shot_data.get("denoise", 0.55)
        new_denoise = max(0.35, current_denoise - 0.05 * retry_num)
        shot_data["denoise"] = new_denoise
        adjustments.append(f"denoise: {current_denoise:.2f} -> {new_denoise:.2f} (consistency)")

        return adjustments

    def _adjust_parameters_for_static(
        self,
        shot_data: dict[str, Any],
        retry_num: int,
    ) -> list[str]:
        """Adjust parameters to produce REAL motion instead of a static frame.

        GPT P0: static videos are caused by denoise clamped too low and too
        few generated frames. Retry must raise denoise, add frames and inject
        motion semantics — never reduce motion.
        """
        adjustments: list[str] = []

        # Raise denoise progressively (0.55 -> 0.60 -> 0.65)
        current_denoise = shot_data.get("denoise", 0.55)
        new_denoise = min(0.70, current_denoise + 0.05 * retry_num)
        shot_data["denoise"] = new_denoise
        adjustments.append(f"denoise: {current_denoise:.2f} -> {new_denoise:.2f} (增加运动)")

        # More generated frames = more room for motion
        current_frames = shot_data.get("frames", 49)
        new_frames = min(161, current_frames + 16 * retry_num)
        shot_data["frames"] = new_frames
        adjustments.append(f"frames: {current_frames} -> {new_frames}")

        # Raise CFG slightly for clearer text-to-motion alignment
        current_cfg = shot_data.get("cfg", 4.5)
        new_cfg = min(6.0, current_cfg + 0.3 * retry_num)
        shot_data["cfg"] = new_cfg
        adjustments.append(f"cfg: {current_cfg:.1f} -> {new_cfg:.1f}")

        # Inject motion semantics into the prompt
        current_prompt = shot_data.get("positive_prompt", "")
        motion_prompt = (
            "natural body movement, subtle breathing, realistic motion, "
            "dynamic pose transition, smooth animation, camera movement"
        )
        if "natural body movement" not in current_prompt.lower():
            shot_data["positive_prompt"] = f"{current_prompt}, {motion_prompt}"
            adjustments.append("prompt: 加入运动语义 (Action/Camera/Motion)")

        return adjustments

    def analyze_and_adjust(
        self,
        shot_data: dict[str, Any],
        quality_issues: list[str],
        retry_num: int,
    ) -> list[str]:
        """Analyze quality issues and adjust shot parameters accordingly.

        Args:
            shot_data: Shot configuration dict (modified in-place).
            quality_issues: List of issue strings from QualityReport.issues.
            retry_num: Current retry attempt number (1-based).

        Returns:
            List of adjustment descriptions for logging.
        """
        all_adjustments: list[str] = []

        for issue in quality_issues:
            if issue in ("static_video", "low_motion", "low_motion_flow", "motion_unanalyzable"):
                all_adjustments.extend(
                    self._adjust_parameters_for_static(shot_data, retry_num)
                )
            elif issue == "mosaic":
                all_adjustments.extend(
                    self._adjust_parameters_for_mosaic(shot_data, retry_num)
                )
            elif issue in ("flickering", "motion_blur"):
                all_adjustments.extend(
                    self._adjust_parameters_for_flickering(shot_data, retry_num)
                )
            elif issue == "too_dark":
                all_adjustments.extend(
                    self._adjust_parameters_for_dark(shot_data, retry_num)
                )
            elif issue == "too_bright":
                all_adjustments.extend(
                    self._adjust_parameters_for_bright(shot_data, retry_num)
                )
            elif issue == "low_consistency":
                all_adjustments.extend(
                    self._adjust_parameters_for_low_consistency(shot_data, retry_num)
                )

        return all_adjustments

    def should_retry(
        self,
        shot_id: str,
        quality_score: float,
        passed: bool,
    ) -> bool:
        """Determine if a shot should be retried.

        Args:
            shot_id: Shot identifier.
            quality_score: Quality score from the last attempt (0-100).
            passed: Whether the quality gate passed.

        Returns:
            True if retry is recommended, False otherwise.
        """
        if passed:
            return False

        current_count = self._retry_history.get(shot_id, 0)
        if current_count >= self.max_retries:
            logger.warning(
                "Shot %s has reached max retries (%d), stopping",
                shot_id, self.max_retries,
            )
            return False

        # Track quality history for trend analysis
        history = self._quality_history.setdefault(shot_id, [])
        history.append(quality_score)

        # If quality is improving, keep retrying
        if len(history) >= 2:
            if history[-1] > history[-2]:
                return True
            # If quality is stagnant or degrading, stop after 2 attempts
            if len(history) >= 3 and history[-1] <= history[-2]:
                logger.warning(
                    "Shot %s quality not improving (history: %s), stopping",
                    shot_id, [f"{s:.1f}" for s in history],
                )
                return False

        # Very low quality (< 30) should always retry
        if quality_score < 30:
            return True

        return True

    def record_attempt(
        self,
        shot_id: str,
        adjustments: list[str],
        quality_score: float,
        passed: bool,
        failure_reasons: list[str] | None = None,
    ) -> None:
        """Record a retry attempt for tracking.

        Args:
            shot_id: Shot identifier.
            adjustments: List of parameter adjustments made.
            quality_score: Quality score achieved (0-100).
            passed: Whether the quality gate passed.
            failure_reasons: Reasons for failure if not passed.
        """
        self._retry_history[shot_id] = self._retry_history.get(shot_id, 0) + 1
        attempt = RetryAttempt(
            attempt_number=self._retry_history[shot_id],
            adjustments=adjustments,
            quality_score=quality_score,
            passed=passed,
            failure_reasons=failure_reasons or [],
        )
        logger.info(
            "Retry attempt %d for %s: score=%.1f, passed=%s, adjustments=%s",
            attempt.attempt_number, shot_id, quality_score, passed,
            ", ".join(adjustments) if adjustments else "none",
        )

    def get_retry_count(self, shot_id: str) -> int:
        """Get the number of retries attempted for a shot."""
        return self._retry_history.get(shot_id, 0)

    def reset(self, shot_id: str) -> None:
        """Reset retry history for a shot (e.g., after manual regeneration)."""
        self._retry_history.pop(shot_id, None)
        self._quality_history.pop(shot_id, None)


# Module-level singleton for convenience
_controller: RetryController | None = None


def get_retry_controller() -> RetryController:
    """Get the singleton RetryController instance."""
    global _controller
    if _controller is None:
        _controller = RetryController()
    return _controller
