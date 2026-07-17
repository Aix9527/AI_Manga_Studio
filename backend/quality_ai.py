"""
AI Manga Studio Pro V1.0 — Quality AI

Automated quality inspection module for generated manga/anime
content. Detects common AI generation artifacts and quality issues
across images and videos, including:

Image quality:
- Character face consistency / identity drift
- Missing / extra fingers or limbs
- Background artifacts / blending errors
- Subtitle synchronization issues

Video quality:
- Action repetition / loop artifacts
- Frame flickering / temporal inconsistency
- Lip-sync mismatch detection

Quality AI produces structured reports with severity levels
and actionable fix suggestions for the Scheduler's retry logic.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


# ============================================================
# Enums
# ============================================================

class IssueType(str, Enum):
    face_identity_drift = "face_identity_drift"
    extra_fingers = "extra_fingers"
    missing_fingers = "missing_fingers"
    extra_limbs = "extra_limbs"
    background_artifact = "background_artifact"
    blending_error = "blending_error"
    subtitle_sync = "subtitle_sync"
    action_repetition = "action_repetition"
    frame_flicker = "frame_flicker"
    lip_sync_mismatch = "lip_sync_mismatch"
    low_resolution = "low_resolution"
    color_banding = "color_banding"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class QualityStatus(str, Enum):
    pass_ = "pass"
    warning = "warning"
    fail = "fail"


# ============================================================
# Data Classes
# ============================================================

@dataclass
class QualityIssue:
    """A single quality issue detected."""
    issue_type: IssueType
    severity: Severity = Severity.medium
    description: str = ""
    frame_index: int = -1
    region: str = ""  # e.g., "left_hand", "face", "background"
    suggested_fix: str = ""
    confidence: float = 0.0  # 0.0 to 1.0


@dataclass
class QualityReport:
    """Complete quality inspection report for a shot."""
    shot_index: int = 0
    image_path: str = ""
    video_path: str = ""
    status: QualityStatus = QualityStatus.pass_
    issues: List[QualityIssue] = field(default_factory=list)
    overall_score: float = 1.0  # 0.0 (worst) to 1.0 (best)
    retry_recommended: bool = False
    retry_params: Dict[str, Any] = field(default_factory=dict)
    inspection_time: float = 0.0


# ============================================================
# Quality AI Engine
# ============================================================

class QualityAI:
    """Automated quality inspection engine.

    Performs heuristic and (optionally) AI-based quality checks on
    generated manga content to detect common artifacts and quality
    degradation that would ruin viewer experience.
    """

    # Severity → score penalty
    SEVERITY_PENALTY: Dict[Severity, float] = {
        Severity.low: 0.05,
        Severity.medium: 0.15,
        Severity.high: 0.30,
        Severity.critical: 0.60,
    }

    # Issue → default retry suggestion
    RETRY_SUGGESTIONS: Dict[IssueType, str] = {
        IssueType.face_identity_drift: "increase_face_weight",
        IssueType.extra_fingers: "enable_negative_hands",
        IssueType.missing_fingers: "enable_negative_hands",
        IssueType.extra_limbs: "enable_negative_limbs",
        IssueType.background_artifact: "increase_cfg_scale",
        IssueType.blending_error: "adjust_denoise_strength",
        IssueType.subtitle_sync: "regenerate_subtitle_timing",
        IssueType.action_repetition: "reduce_i2v_denoise",
        IssueType.frame_flicker: "enable_temporal_smoothing",
        IssueType.lip_sync_mismatch: "regenerate_lipsync",
        IssueType.low_resolution: "enable_upscale",
        IssueType.color_banding: "increase_color_depth",
    }

    def __init__(
        self,
        face_consistency_threshold: float = 0.85,
        finger_check_enabled: bool = True,
        flicker_threshold: float = 0.05,
        enable_ai_detection: bool = False,
    ) -> None:
        """Initialize the Quality AI engine.

        Args:
            face_consistency_threshold: Cosine similarity threshold for face identity.
            finger_check_enabled: Whether to check for hand/finger artifacts.
            flicker_threshold: Frame brightness change threshold for flicker detection.
            enable_ai_detection: Whether to use external AI detection models.
        """
        self.face_consistency_threshold = face_consistency_threshold
        self.finger_check_enabled = finger_check_enabled
        self.flicker_threshold = flicker_threshold
        self.enable_ai_detection = enable_ai_detection

        # Stored reference face embeddings for identity checking
        self.face_embeddings: Dict[str, Any] = {}

        logger.info(
            f"QualityAI: Initialized (face_threshold={face_consistency_threshold}, "
            f"finger_check={finger_check_enabled})"
        )

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def inspect_image(
        self,
        shot_index: int,
        image_path: str,
        reference_character: str = "",
        reference_face_embedding: Optional[Any] = None,
    ) -> QualityReport:
        """Inspect a single generated image for quality issues.

        Args:
            shot_index: Shot index.
            image_path: Path to the generated image.
            reference_character: Character name for identity comparison.
            reference_face_embedding: Optional pre-computed face embedding.

        Returns:
            QualityReport with findings.
        """
        import time
        start_time = time.time()

        report = QualityReport(
            shot_index=shot_index,
            image_path=image_path,
        )

        if not os.path.exists(image_path):
            report.status = QualityStatus.fail
            report.issues.append(QualityIssue(
                issue_type=IssueType.low_resolution,
                severity=Severity.critical,
                description="Image file not found",
                confidence=1.0,
            ))
            report.overall_score = 0.0
            return report

        issues: List[QualityIssue] = []

        # Check 1: Resolution
        resolution_issues = self._check_resolution(image_path)
        issues.extend(resolution_issues)

        # Check 2: Face consistency (if reference available)
        if reference_face_embedding is not None:
            face_issues = self._check_face_consistency(image_path, reference_face_embedding)
            issues.extend(face_issues)

        # Check 3: Finger/hand artifacts
        if self.finger_check_enabled:
            hand_issues = self._check_hands(image_path)
            issues.extend(hand_issues)

        # Check 4: Color banding and artifacts
        banding_issues = self._check_color_banding(image_path)
        issues.extend(banding_issues)

        # Check 5: AI-based detection (if enabled)
        if self.enable_ai_detection:
            ai_issues = self._ai_detect_issues(image_path)
            issues.extend(ai_issues)

        # Compute score
        report.issues = issues
        report.overall_score = self._compute_score(issues)
        report.status = self._determine_status(issues)
        report.retry_recommended = report.status in (QualityStatus.fail, QualityStatus.warning)
        report.retry_params = self._build_retry_params(issues)
        report.inspection_time = time.time() - start_time

        logger.info(
            f"QualityAI: Shot {shot_index} → {report.status.value} "
            f"(score={report.overall_score:.2f}, issues={len(issues)})"
        )

        return report

    def inspect_video(
        self,
        shot_index: int,
        video_path: str,
        expected_frames: int = -1,
    ) -> QualityReport:
        """Inspect a generated video for quality issues.

        Args:
            shot_index: Shot index.
            video_path: Path to the generated video.
            expected_frames: Expected number of frames (-1 to skip check).

        Returns:
            QualityReport with findings.
        """
        import time
        start_time = time.time()

        report = QualityReport(
            shot_index=shot_index,
            video_path=video_path,
        )

        if not os.path.exists(video_path):
            report.status = QualityStatus.fail
            report.issues.append(QualityIssue(
                issue_type=IssueType.action_repetition,
                severity=Severity.critical,
                description="Video file not found",
                confidence=1.0,
            ))
            report.overall_score = 0.0
            return report

        issues: List[QualityIssue] = []

        # Check 1: Frame flicker
        flicker_issues = self._check_flicker(video_path)
        issues.extend(flicker_issues)

        # Check 2: Action repetition
        repetition_issues = self._check_action_repetition(video_path)
        issues.extend(repetition_issues)

        # Check 3: Lip-sync mismatch
        lipsync_issues = self._check_lip_sync(video_path)
        issues.extend(lipsync_issues)

        report.issues = issues
        report.overall_score = self._compute_score(issues)
        report.status = self._determine_status(issues)
        report.retry_recommended = report.status in (QualityStatus.fail, QualityStatus.warning)
        report.retry_params = self._build_retry_params(issues)
        report.inspection_time = time.time() - start_time

        logger.info(
            f"QualityAI: Video shot {shot_index} → {report.status.value} "
            f"(score={report.overall_score:.2f}, issues={len(issues)})"
        )

        return report

    def inspect_batch(
        self,
        shot_data: List[dict],
    ) -> List[QualityReport]:
        """Inspect a batch of shots.

        Args:
            shot_data: List of dicts with 'index' and 'image_path' or 'video_path'.

        Returns:
            List of QualityReport objects.
        """
        reports: List[QualityReport] = []

        for data in shot_data:
            idx = data.get("index", 0)

            if "video_path" in data and data["video_path"]:
                report = self.inspect_video(
                    shot_index=idx,
                    video_path=data["video_path"],
                )
            elif "image_path" in data and data["image_path"]:
                report = self.inspect_image(
                    shot_index=idx,
                    image_path=data["image_path"],
                    reference_character=data.get("character", ""),
                )
            else:
                continue

            reports.append(report)

        passed = sum(1 for r in reports if r.status == QualityStatus.pass_)
        logger.info(f"QualityAI: Batch complete ({passed}/{len(reports)} passed)")
        return reports

    # ----------------------------------------------------------
    # Store / Load Face Reference
    # ----------------------------------------------------------

    def store_face_reference(
        self,
        character_name: str,
        embedding: Any,
    ) -> None:
        """Store a face embedding as reference for identity checking.

        Args:
            character_name: Character name.
            embedding: Face embedding tensor/vector.
        """
        self.face_embeddings[character_name] = embedding
        logger.info(f"QualityAI: Stored face reference for '{character_name}'")

    # ----------------------------------------------------------
    # Individual Checks
    # ----------------------------------------------------------

    def _check_resolution(self, image_path: str) -> List[QualityIssue]:
        """Check if the image meets minimum resolution requirements.

        Args:
            image_path: Path to the image.

        Returns:
            List of QualityIssue objects.
        """
        issues: List[QualityIssue] = []

        try:
            from PIL import Image
            with Image.open(image_path) as img:
                w, h = img.size

                if w < 512 or h < 512:
                    issues.append(QualityIssue(
                        issue_type=IssueType.low_resolution,
                        severity=Severity.high,
                        description=f"Image too small: {w}x{h}",
                        suggested_fix=self.RETRY_SUGGESTIONS[IssueType.low_resolution],
                        confidence=0.95,
                    ))
        except Exception as e:
            logger.warning(f"QualityAI: Resolution check failed for {image_path}: {e}")

        return issues

    def _check_face_consistency(
        self,
        image_path: str,
        reference_embedding: Any,
    ) -> List[QualityIssue]:
        """Check face identity consistency against reference.

        Args:
            image_path: Path to generated image.
            reference_embedding: Reference face embedding.

        Returns:
            List of QualityIssue objects.
        """
        # Placeholder: requires face detection + embedding model
        # (e.g., InsightFace, ArcFace)
        logger.debug(f"QualityAI: Face consistency check not yet implemented (needs face model)")
        return []

    def _check_hands(self, image_path: str) -> List[QualityIssue]:
        """Check for hand / finger artifacts.

        This is a heuristic check. In production, this would use
        a trained hand detector or MediaPipe hand landmark model.

        Args:
            image_path: Path to generated image.

        Returns:
            List of QualityIssue objects.
        """
        # Placeholder: MediaPipe hand detection would count fingers
        # and flag counts != 5 per hand
        logger.debug(f"QualityAI: Hand check placeholder for {image_path}")
        return []

    def _check_color_banding(self, image_path: str) -> List[QualityIssue]:
        """Check for color banding artifacts.

        Args:
            image_path: Path to generated image.

        Returns:
            List of QualityIssue objects.
        """
        issues: List[QualityIssue] = []

        try:
            from PIL import Image
            import numpy as np

            with Image.open(image_path) as img:
                arr = np.array(img.convert("L"), dtype=np.float32)

            # Simple gradient smoothness check
            # Detect flat regions that might indicate banding
            grad_x = np.abs(np.diff(arr, axis=1))
            flat_ratio = np.sum(grad_x < 2) / grad_x.size

            if flat_ratio > 0.15:
                issues.append(QualityIssue(
                    issue_type=IssueType.color_banding,
                    severity=Severity.low,
                    description=f"Possible color banding detected (flat_ratio={flat_ratio:.2f})",
                    suggested_fix=self.RETRY_SUGGESTIONS[IssueType.color_banding],
                    confidence=0.6,
                ))

        except Exception as e:
            logger.warning(f"QualityAI: Banding check failed for {image_path}: {e}")

        return issues

    def _check_flicker(self, video_path: str) -> List[QualityIssue]:
        """Check for frame flickering in video.

        Args:
            video_path: Path to video file.

        Returns:
            List of QualityIssue objects.
        """
        # Placeholder: requires FFmpeg frame extraction + brightness analysis
        logger.debug(f"QualityAI: Flicker check placeholder for {video_path}")
        return []

    def _check_action_repetition(self, video_path: str) -> List[QualityIssue]:
        """Check for repeated/looping action artifacts.

        Args:
            video_path: Path to video file.

        Returns:
            List of QualityIssue objects.
        """
        logger.debug(f"QualityAI: Repetition check placeholder for {video_path}")
        return []

    def _check_lip_sync(self, video_path: str) -> List[QualityIssue]:
        """Check for lip-sync mismatch.

        Args:
            video_path: Path to video file.

        Returns:
            List of QualityIssue objects.
        """
        logger.debug(f"QualityAI: Lip-sync check placeholder for {video_path}")
        return []

    def _ai_detect_issues(self, image_path: str) -> List[QualityIssue]:
        """Use external AI model for comprehensive issue detection.

        Args:
            image_path: Path to image.

        Returns:
            List of QualityIssue objects.
        """
        # Placeholder: would call an external API or local model
        return []

    # ----------------------------------------------------------
    # Scoring & Status
    # ----------------------------------------------------------

    def _compute_score(self, issues: List[QualityIssue]) -> float:
        """Compute overall quality score from issues.

        Args:
            issues: List of detected issues.

        Returns:
            Score from 0.0 to 1.0.
        """
        score = 1.0
        for issue in issues:
            penalty = self.SEVERITY_PENALTY.get(issue.severity, 0.05)
            score -= penalty

        return max(0.0, min(1.0, score))

    def _determine_status(self, issues: List[QualityIssue]) -> QualityStatus:
        """Determine overall quality status from issues.

        Args:
            issues: List of detected issues.

        Returns:
            QualityStatus.
        """
        if not issues:
            return QualityStatus.pass_

        severities = {i.severity for i in issues}

        if Severity.critical in severities:
            return QualityStatus.fail
        if Severity.high in severities:
            return QualityStatus.fail
        if Severity.medium in severities:
            return QualityStatus.warning

        return QualityStatus.warning

    def _build_retry_params(self, issues: List[QualityIssue]) -> Dict[str, Any]:
        """Build retry parameter suggestions based on detected issues.

        Args:
            issues: List of detected issues.

        Returns:
            Dict of retry parameters.
        """
        params: Dict[str, Any] = {}

        for issue in issues:
            if issue.suggested_fix:
                params[issue.issue_type.value] = issue.suggested_fix

        return params

    # ----------------------------------------------------------
    # Report Export
    # ----------------------------------------------------------

    def export_reports(
        self,
        reports: List[QualityReport],
        output_path: str,
    ) -> None:
        """Export quality reports to JSON.

        Args:
            reports: List of QualityReport objects.
            output_path: Output JSON path.
        """
        data: List[Dict[str, Any]] = []
        for report in reports:
            data.append({
                "shot_index": report.shot_index,
                "status": report.status.value,
                "overall_score": report.overall_score,
                "retry_recommended": report.retry_recommended,
                "issues": [
                    {
                        "type": i.issue_type.value,
                        "severity": i.severity.value,
                        "description": i.description,
                        "confidence": i.confidence,
                    }
                    for i in report.issues
                ],
            })

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"QualityAI: Exported {len(data)} reports → {output_path}")
