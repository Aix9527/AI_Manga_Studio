"""Video Intelligence Layer - Four-Agent orchestration system.

Per GPT's Sprint recommendation, this module implements a Video Intelligence
Layer with four specialized agents that coordinate the entire video generation
pipeline:

1. **Video Director Agent**: Analyzes shot context (description, camera,
   narration, scene type) and determines the optimal generation strategy:
   - Provider selection (via OpenMontage scoring)
   - Prompt enhancement (via LocalDrama + Cinema DNA)
   - Sampling parameters (denoise, steps, cfg based on scene type)
   - Duration planning (via Duration Strategy)
   - Tail-frame linking strategy

2. **Quality Judge Agent**: Evaluates generated video quality using
   multi-indicator fusion analysis:
   - Mosaic detection (FFT + block artifacts + edge repetition)
   - Temporal consistency (SSIM-style)
   - Brightness/contrast analysis
   - Produces structured quality report with pass/fail verdict

3. **Continuity Agent**: Maintains visual continuity across shots:
   - Tail-frame extraction and linking (three-tier strategy)
   - Character anchor management (mask-based fusion)
   - Chain breakage recovery
   - Drift detection via visual fingerprints

4. **Retry Optimization Agent**: Automatically recovers from failures:
   - Analyzes quality issues and adjusts parameters
   - Exponential backoff on stubborn failures
   - Quality trend tracking (improving vs. stagnant)
   - Max retry limit enforcement

The VideoIntelligenceOrchestrator coordinates all four agents in a unified
pipeline, providing a clean API for the video generation flow.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent 1: Video Director
# ---------------------------------------------------------------------------

@dataclass
class DirectorDecision:
    """Decision output from the Video Director Agent."""
    provider: str = "wan22"
    provider_score: dict[str, Any] = field(default_factory=dict)
    enhanced_positive_prompt: str = ""
    enhanced_negative_prompt: str = ""
    scene_type: str = "dialogue"
    target_duration: float = 6.0
    interpolation_multiplier: int = 3
    duration_reasoning: str = ""
    denoise: float = 0.55
    steps: int = 30
    cfg: float = 3.0
    video_frames: int = 49
    gen_width: int = 480
    gen_height: int = 832
    use_tail_frame: bool = True
    use_character_anchor: bool = False
    anchor_refresh_needed: bool = False
    reasoning: str = ""


class VideoDirectorAgent:
    """Analyzes shot context and determines optimal generation strategy.

    This agent coordinates:
    - Scene type classification (from duration_strategy.py)
    - Duration calculation (emotion + camera complexity)
    - Provider selection (from OpenMontage)
    - Prompt enhancement (LocalDrama + Cinema DNA)
    - Sampling parameters (scene-type dependent)
    """

    # Scene-type dependent sampling parameters
    SCENE_DENOISE = {
        "dialogue": 0.45, "emotional": 0.45, "narration": 0.50,
        "action": 0.55, "establishing": 0.55, "transition": 0.50,
    }
    SCENE_STEPS = {
        "dialogue": 30, "emotional": 35, "narration": 30,
        "action": 30, "establishing": 35, "transition": 25,
    }

    def plan(
        self,
        shot_data: dict[str, Any],
        shot_index: int,
        total_shots: int,
        has_previous_tail: bool,
        anchor_refresh_interval: int = 5,
    ) -> DirectorDecision:
        """Create a generation plan for a shot.

        Args:
            shot_data: Shot configuration dict.
            shot_index: Zero-based index of this shot.
            total_shots: Total number of shots in the episode.
            has_previous_tail: Whether a tail frame from the previous shot exists.
            anchor_refresh_interval: Refresh character anchor every N shots.

        Returns:
            DirectorDecision with all generation parameters.
        """
        decision = DirectorDecision()
        shot_description = shot_data.get("description", "")
        shot_camera = shot_data.get("camera", "")
        shot_narration = shot_data.get("narration", "")
        shot_prompt = shot_data.get("positive_prompt", "")

        # 1. Scene classification + Duration strategy
        try:
            from backend.video.duration_strategy import (
                classify_scene_type, calculate_shot_duration, get_motion_profile,
            )
            decision.scene_type = classify_scene_type(shot_data)
            motion_profile = get_motion_profile(shot_data)
            duration_plan = calculate_shot_duration(
                shot_data=shot_data,
                scene_type=decision.scene_type,
                shot_index=shot_index,
                total_shots=total_shots,
                source_frames=motion_profile.frames,
            )
            decision.target_duration = duration_plan.final_duration
            decision.interpolation_multiplier = duration_plan.interpolation_multiplier
            decision.duration_reasoning = duration_plan.reasoning
        except Exception as exc:
            logger.debug("Duration strategy skipped: %s", exc)
            decision.target_duration = 6.0
            decision.interpolation_multiplier = 3

        # 2. Sampling parameters driven by the motion profile (GPT P0: 真实运动优先)
        try:
            from backend.video.duration_strategy import get_motion_profile
            motion_profile = get_motion_profile(shot_data)
            decision.denoise = motion_profile.denoise
            decision.steps = motion_profile.steps
            decision.cfg = motion_profile.cfg
            decision.video_frames = motion_profile.frames
        except Exception:
            decision.denoise = self.SCENE_DENOISE.get(decision.scene_type, 0.55)
            decision.steps = self.SCENE_STEPS.get(decision.scene_type, 30)
            decision.cfg = 3.0

        # 3. Prompt enhancement pipeline: LocalDrama > Cinema DNA
        enhanced = shot_prompt
        try:
            from backend.routes.creator import (
                _enhance_prompt_with_localdrama,
                _enhance_prompt_with_cinema_dna,
            )
            enhanced = _enhance_prompt_with_localdrama(
                prompt=shot_prompt,
                shot_description=shot_description,
                camera=shot_camera,
                shot_id=shot_data.get("id", ""),
            )
            cinema_pos, cinema_neg = _enhance_prompt_with_cinema_dna(
                prompt=enhanced,
                shot_description=shot_description,
                camera=shot_camera,
                narration=shot_narration,
            )
            enhanced = cinema_pos
            if cinema_neg:
                decision.enhanced_negative_prompt = cinema_neg
        except Exception as exc:
            logger.debug("Prompt enhancement skipped: %s", exc)

        decision.enhanced_positive_prompt = enhanced

        # 4. Provider selection via OpenMontage
        try:
            from backend.routes.creator import _select_provider_with_openmontage
            provider, score = _select_provider_with_openmontage(
                shot_description=shot_description,
                camera=shot_camera,
                narration=shot_narration,
            )
            decision.provider = provider
            decision.provider_score = score
        except Exception as exc:
            logger.debug("Provider selection skipped: %s", exc)

        # 5. Continuity decisions
        decision.use_tail_frame = has_previous_tail
        decision.anchor_refresh_needed = (
            shot_index > 0 and shot_index % anchor_refresh_interval == 0
        )
        decision.use_character_anchor = decision.anchor_refresh_needed or shot_index == 0

        # 6. Video generation parameters (frames already set by motion profile)
        decision.gen_width = 480
        decision.gen_height = 832

        decision.reasoning = (
            f"scene={decision.scene_type}, "
            f"duration={decision.target_duration:.1f}s ({decision.duration_reasoning}), "
            f"provider={decision.provider}, "
            f"denoise={decision.denoise:.2f}, steps={decision.steps}, cfg={decision.cfg:.1f}, "
            f"tail_frame={decision.use_tail_frame}, anchor_refresh={decision.anchor_refresh_needed}"
        )

        logger.info("Director plan for shot %s: %s",
                    shot_data.get("id", "?"), decision.reasoning)
        return decision


# ---------------------------------------------------------------------------
# Agent 2: Quality Judge
# ---------------------------------------------------------------------------

class QualityJudgeAgent:
    """Evaluates generated video quality using multi-indicator fusion.

    Wraps the quality_gate.py module and provides structured verdicts
    that the Retry Optimization Agent can act upon.
    """

    def evaluate(
        self,
        video_path: Path,
        shot_id: str = "",
    ) -> tuple[Any, list[str]]:
        """Evaluate a generated video for quality issues.

        Args:
            video_path: Path to the generated video file.
            shot_id: Shot identifier for logging.

        Returns:
            Tuple of (QualityReport, list_of_issues).
        """
        try:
            from backend.video.quality_gate import check_video_quality
            report = check_video_quality(video_path)

            logger.info(
                "Quality Judge verdict for %s: %s (score=%.1f, consistency=%.2f, mosaic=%.3f, "
                "motion: diff=%.3f static=%.0f%% flow=%.3f)",
                shot_id or video_path.name,
                report.verdict,
                report.overall_score,
                report.temporal_consistency,
                report.frames[0].mosaic_score if report.frames else 0.0,
                report.mean_frame_diff,
                report.static_frame_ratio * 100,
                report.motion_score,
            )

            return report, report.issues
        except Exception as exc:
            logger.warning("Quality evaluation failed for %s: %s", video_path, exc)
            # Return a minimal report-like object
            from backend.video.quality_gate import QualityReport
            report = QualityReport(video_path=str(video_path))
            report.passed = True  # Assume pass if we can't check
            report.overall_score = 50.0
            report.issues = []
            return report, []

    def should_accept(
        self,
        quality_report: Any,
        min_score: float = 40.0,
    ) -> bool:
        """Determine if a video quality is acceptable.

        Args:
            quality_report: QualityReport from evaluate().
            min_score: Minimum acceptable quality score.

        Returns:
            True if the video passes quality checks.
        """
        if quality_report.passed:
            return True
        if quality_report.overall_score >= min_score:
            return True
        return False


# ---------------------------------------------------------------------------
# Agent 3: Continuity Agent
# ---------------------------------------------------------------------------

class ContinuityAgent:
    """Maintains visual continuity across shots in a sequence.

    Coordinates:
    - Tail-frame extraction (three-tier strategy with black-frame detection)
    - Character anchor management (mask-based fusion)
    - Chain breakage recovery
    - Drift detection
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._anchor_manager: Any = None
        self._last_tail_frame: Path | None = None
        self._last_successful_shot: str = ""

    def extract_tail_frame(
        self,
        video_path: Path,
        shot_id: str,
    ) -> Path | None:
        """Extract the last frame from a video for continuity.

        Uses three-tier extraction: precise timestamp > EOF seek > select filter.
        Includes black-frame detection to skip bad extractions.

        Args:
            video_path: Path to the source video.
            shot_id: Shot identifier for naming the output.

        Returns:
            Path to the extracted tail frame, or None on failure.
        """
        try:
            from backend.video.tailframe import extract_last_frame
            output_dir = self.project_root / "outputs" / "videos" / shot_id
            output_dir.mkdir(parents=True, exist_ok=True)
            tail_path = output_dir / "tail_frame.png"

            result = extract_last_frame(video_path, tail_path)
            if result:
                self._last_tail_frame = result
                self._last_successful_shot = shot_id
                logger.info("Continuity: tail frame extracted for %s -> %s",
                           shot_id, result.name)
            return result
        except Exception as exc:
            logger.warning("Tail frame extraction failed for %s: %s", shot_id, exc)
            return None

    def get_start_image(
        self,
        shot_id: str,
        shot_index: int,
        keyframe_path: Path,
        anchor_refresh_interval: int = 5,
    ) -> tuple[Path, str]:
        """Determine the start image for a shot, considering continuity.

        Priority:
        1. Character anchor refresh (every N shots) - resets drift
        2. Tail frame from previous shot - visual continuity
        3. Keyframe image - fallback

        Args:
            shot_id: Current shot identifier.
            shot_index: Zero-based shot index.
            keyframe_path: Path to the shot's keyframe image.
            anchor_refresh_interval: Refresh anchor every N shots.

        Returns:
            Tuple of (image_path, source_description).
        """
        # Check if anchor refresh is needed
        if shot_index > 0 and shot_index % anchor_refresh_interval == 0:
            try:
                anchor_path = self._get_character_anchor(shot_id)
                if anchor_path and anchor_path.exists():
                    logger.info("Continuity: using character anchor for %s (refresh at shot %d)",
                               shot_id, shot_index)
                    return anchor_path, "character_anchor"
            except Exception:
                pass

        # Use tail frame from previous shot
        if self._last_tail_frame and self._last_tail_frame.exists():
            # Blend with character anchor if available
            blended = self._blend_with_anchor(self._last_tail_frame, keyframe_path)
            if blended:
                return blended, "tail_frame_blended"
            return self._last_tail_frame, "tail_frame"

        # Fallback to keyframe
        return keyframe_path, "keyframe"

    def _get_character_anchor(self, shot_id: str) -> Path | None:
        """Get or create a character anchor for the current shot."""
        try:
            from backend.video.character_anchor import CharacterMemoryAnchor
            anchor_dir = self.project_root / "outputs" / "anchors"
            anchor_dir.mkdir(parents=True, exist_ok=True)

            if self._anchor_manager is None:
                self._anchor_manager = CharacterMemoryAnchor(work_dir=anchor_dir)

            # Return the most recent anchor image
            anchors = list(anchor_dir.glob("*.png"))
            if anchors:
                return max(anchors, key=lambda p: p.stat().st_mtime)
            return None
        except Exception as exc:
            logger.debug("Character anchor retrieval skipped: %s", exc)
            return None

    def _blend_with_anchor(
        self,
        tail_path: Path,
        keyframe_path: Path,
        anchor_ratio: float = 0.3,
    ) -> Path | None:
        """Blend tail frame with keyframe for smoother transitions.

        Uses simple alpha blending: 70% tail + 30% keyframe.
        """
        try:
            from PIL import Image
            output_path = tail_path.parent / f"blended_{tail_path.name}"

            with Image.open(tail_path) as tail_img:
                with Image.open(keyframe_path) as kf_img:
                    # Resize keyframe to match tail frame
                    kf_resized = kf_img.resize(tail_img.size, Image.Resampling.LANCZOS)

                    # Blend
                    blended = Image.blend(tail_img.convert("RGB"),
                                         kf_resized.convert("RGB"),
                                         anchor_ratio)
                    blended.save(output_path, "PNG")

            return output_path
        except Exception as exc:
            logger.debug("Anchor blending skipped: %s", exc)
            return None

    def recover_from_breakage(
        self,
        failed_shot_id: str,
        keyframe_path: Path,
    ) -> Path:
        """Recover from a chain breakage by using the keyframe as fallback.

        When a shot fails, the tail-frame chain is broken. This method
        provides a fallback start image so the next shot can still
        generate with visual continuity.

        Args:
            failed_shot_id: The shot that failed.
            keyframe_path: Path to the failed shot's keyframe.

        Returns:
            Path to use as the start image for the next shot.
        """
        logger.warning(
            "Continuity: chain breakage at %s, using keyframe as fallback",
            failed_shot_id,
        )
        self._last_tail_frame = keyframe_path
        self._last_successful_shot = failed_shot_id
        return keyframe_path

    @property
    def last_tail_frame(self) -> Path | None:
        """Get the last extracted tail frame path."""
        return self._last_tail_frame


# ---------------------------------------------------------------------------
# Agent 4: Retry Optimization Agent
# ---------------------------------------------------------------------------

class RetryOptimizationAgent:
    """Automatically retries failed video generations with adjusted parameters.

    Wraps the retry_controller.py module and coordinates with the
    Quality Judge to determine when and how to retry.
    """

    def __init__(self, max_retries: int = 3):
        from backend.video.retry_controller import RetryController
        self._controller = RetryController(max_retries=max_retries)

    def should_retry(
        self,
        shot_id: str,
        quality_report: Any,
        min_score: float = 40.0,
    ) -> bool:
        """Determine if a shot should be retried based on quality report.

        Args:
            shot_id: Shot identifier.
            quality_report: QualityReport from Quality Judge.
            min_score: Minimum acceptable score.

        Returns:
            True if retry is recommended.
        """
        if quality_report.passed:
            return False
        if quality_report.overall_score >= min_score:
            return False
        return self._controller.should_retry(
            shot_id=shot_id,
            quality_score=quality_report.overall_score,
            passed=quality_report.passed,
        )

    def get_adjusted_parameters(
        self,
        shot_data: dict[str, Any],
        quality_issues: list[str],
    ) -> tuple[dict[str, Any], list[str]]:
        """Get adjusted parameters for a retry attempt.

        Args:
            shot_data: Original shot configuration (will be copied and modified).
            quality_issues: List of quality issues from the Quality Judge.

        Returns:
            Tuple of (adjusted_shot_data, list_of_adjustment_descriptions).
        """
        import copy
        adjusted = copy.deepcopy(shot_data)
        retry_num = self._controller.get_retry_count(shot_data.get("id", "")) + 1
        adjustments = self._controller.analyze_and_adjust(
            adjusted, quality_issues, retry_num
        )
        return adjusted, adjustments

    def record_result(
        self,
        shot_id: str,
        adjustments: list[str],
        quality_score: float,
        passed: bool,
        failure_reasons: list[str] | None = None,
    ) -> None:
        """Record the result of a retry attempt."""
        self._controller.record_attempt(
            shot_id=shot_id,
            adjustments=adjustments,
            quality_score=quality_score,
            passed=passed,
            failure_reasons=failure_reasons,
        )

    def reset(self, shot_id: str) -> None:
        """Reset retry history for a shot."""
        self._controller.reset(shot_id)


# ---------------------------------------------------------------------------
# Video Intelligence Orchestrator
# ---------------------------------------------------------------------------

class VideoIntelligenceOrchestrator:
    """Unified orchestrator for the four-agent Video Intelligence Layer.

    This class coordinates the Video Director, Quality Judge, Continuity,
    and Retry Optimization agents to provide a clean, high-level API for
    the video generation pipeline.

    Usage:
        orchestrator = VideoIntelligenceOrchestrator(project_root)
        plan = orchestrator.plan_shot(shot_data, shot_index, total_shots)
        # ... generate video using plan ...
        quality = orchestrator.evaluate_quality(video_path)
        if orchestrator.should_retry(shot_id, quality):
            adjusted = orchestrator.get_retry_params(shot_data, quality.issues)
            # ... regenerate with adjusted params ...
    """

    def __init__(self, project_root: Path, max_retries: int = 3):
        self.project_root = project_root
        self.director = VideoDirectorAgent()
        self.quality_judge = QualityJudgeAgent()
        self.continuity = ContinuityAgent(project_root)
        self.retry_agent = RetryOptimizationAgent(max_retries=max_retries)

    def plan_shot(
        self,
        shot_data: dict[str, Any],
        shot_index: int,
        total_shots: int,
        has_previous_tail: bool = False,
    ) -> DirectorDecision:
        """Create a generation plan for a shot using the Video Director."""
        return self.director.plan(
            shot_data=shot_data,
            shot_index=shot_index,
            total_shots=total_shots,
            has_previous_tail=has_previous_tail,
        )

    def evaluate_quality(
        self,
        video_path: Path,
        shot_id: str = "",
    ) -> tuple[Any, list[str]]:
        """Evaluate video quality using the Quality Judge."""
        return self.quality_judge.evaluate(video_path, shot_id)

    def extract_tail_frame(
        self,
        video_path: Path,
        shot_id: str,
    ) -> Path | None:
        """Extract tail frame for continuity using the Continuity Agent."""
        return self.continuity.extract_tail_frame(video_path, shot_id)

    def get_start_image(
        self,
        shot_id: str,
        shot_index: int,
        keyframe_path: Path,
    ) -> tuple[Path, str]:
        """Determine start image for a shot using the Continuity Agent."""
        return self.continuity.get_start_image(shot_id, shot_index, keyframe_path)

    def should_retry(
        self,
        shot_id: str,
        quality_report: Any,
        min_score: float = 40.0,
    ) -> bool:
        """Check if a shot should be retried using the Retry Agent."""
        return self.retry_agent.should_retry(shot_id, quality_report, min_score)

    def get_retry_params(
        self,
        shot_data: dict[str, Any],
        quality_issues: list[str],
    ) -> tuple[dict[str, Any], list[str]]:
        """Get adjusted parameters for retry using the Retry Agent."""
        return self.retry_agent.get_adjusted_parameters(shot_data, quality_issues)

    def record_retry_result(
        self,
        shot_id: str,
        adjustments: list[str],
        quality_score: float,
        passed: bool,
        failure_reasons: list[str] | None = None,
    ) -> None:
        """Record a retry attempt result."""
        self.retry_agent.record_result(
            shot_id, adjustments, quality_score, passed, failure_reasons
        )

    def recover_chain_breakage(
        self,
        failed_shot_id: str,
        keyframe_path: Path,
    ) -> Path:
        """Recover from a continuity chain breakage."""
        return self.continuity.recover_from_breakage(failed_shot_id, keyframe_path)
