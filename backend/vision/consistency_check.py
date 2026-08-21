"""
Consistency Check — Sprint 7.1 Vision Critic.
Cross-frame character consistency and style drift detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from backend.vision.image_analyzer import ImageProfile


@dataclass
class ConsistencyReport:
    """Cross-frame consistency assessment."""
    character_id: str = ""
    compared_count: int = 0
    mean_similarity: float = 0.0
    variance: float = 0.0
    drift_detected: bool = False
    consistent: bool = True
    threshold: float = 0.70

    details: list[dict] = field(default_factory=list)


@dataclass
class StyleDriftReport:
    """Art style consistency across a sequence."""
    mean_style_score: float = 0.0
    style_variance: float = 0.0
    drift_detected: bool = False
    affected_shots: list[str] = field(default_factory=list)
    suggestion: str = ""


class ConsistencyChecker:
    """
    Cross-frame consistency checker.

    Tracks character appearance and style across multiple generated frames
    to detect degradation and drift over a sequence.
    """

    def __init__(self, similarity_threshold: float = 0.70):
        self.threshold = similarity_threshold

    def check_character_consistency(
        self,
        character_id: str,
        profiles: list[ImageProfile],
        reference_profile: Optional[ImageProfile] = None,
    ) -> ConsistencyReport:
        """
        Check if a character's appearance is consistent across multiple frames.

        Compares each frame's profile against the reference (or pairwise).
        """
        report = ConsistencyReport(
            character_id=character_id,
            compared_count=len(profiles),
            threshold=self.threshold,
        )

        if len(profiles) < 2:
            report.consistent = True
            return report

        similarities: list[float] = []

        ref = reference_profile or profiles[0]

        for i, profile in enumerate(profiles):
            sim = self._tag_similarity(ref.content_tags, profile.content_tags)
            similarities.append(sim)
            report.details.append({
                "index": i,
                "image_path": profile.image_path,
                "similarity": round(sim, 4),
                "tags": profile.content_tags[:8],
            })

        if similarities:
            report.mean_similarity = round(
                sum(similarities) / len(similarities), 4
            )
            mean = report.mean_similarity
            report.variance = round(
                sum((s - mean) ** 2 for s in similarities) / len(similarities), 4
            )

        report.drift_detected = report.mean_similarity < self.threshold
        report.consistent = not report.drift_detected

        return report

    def check_style_consistency(
        self,
        profiles: list[ImageProfile],
    ) -> StyleDriftReport:
        """
        Check art style consistency across a full sequence.
        Detects degradation if later frames diverge from early ones.
        """
        report = StyleDriftReport()

        if len(profiles) < 3:
            report.mean_style_score = 1.0
            return report

        # Use first frame as reference
        ref_tags = profiles[0].content_tags
        if not ref_tags:
            report.mean_style_score = 0.5
            return report

        style_scores: list[float] = []
        affected: list[str] = []

        ref_set = set(ref_tags)
        for i, profile in enumerate(profiles):
            profile_set = set(profile.content_tags)
            overlap = len(ref_set & profile_set) if ref_set else 0
            score = overlap / len(ref_set) if ref_set else 0
            style_scores.append(score)

            if score < self.threshold:
                affected.append(profile.image_path or f"shot_{i}")

        if style_scores:
            report.mean_style_score = round(
                sum(style_scores) / len(style_scores), 4
            )
            mean = report.mean_style_score
            report.style_variance = round(
                sum((s - mean) ** 2 for s in style_scores) / len(style_scores), 4
            )

        # Drift detection: later frames significantly worse than early frames
        if len(style_scores) >= 3:
            early = style_scores[: len(style_scores) // 2]
            late = style_scores[len(style_scores) // 2 :]
            early_mean = sum(early) / len(early) if early else 1.0
            late_mean = sum(late) / len(late) if late else 1.0

            if early_mean - late_mean > 0.15:  # noticeable degradation
                report.drift_detected = True
                report.suggestion = (
                    "Style degradation detected in later frames. "
                    "Consider adding stronger style anchors to prompts "
                    "or increasing CFG scale to maintain consistency."
                )

        report.affected_shots = affected
        return report

    def pairwise_consistency_matrix(
        self, profiles: list[ImageProfile]
    ) -> list[list[float]]:
        """Build an N×N similarity matrix for N profiles."""
        n = len(profiles)
        matrix: list[list[float]] = [[1.0] * n for _ in range(n)]

        for i in range(n):
            for j in range(i + 1, n):
                sim = self._tag_similarity(
                    profiles[i].content_tags, profiles[j].content_tags
                )
                matrix[i][j] = sim
                matrix[j][i] = sim

        return matrix

    @staticmethod
    def _tag_similarity(tags_a: list[str], tags_b: list[str]) -> float:
        """Compute Jaccard similarity between two tag sets."""
        set_a = set(tags_a)
        set_b = set(tags_b)

        if not set_a and not set_b:
            return 1.0
        if not set_a or not set_b:
            return 0.0

        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0
