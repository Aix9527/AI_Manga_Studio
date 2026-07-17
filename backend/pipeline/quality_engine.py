"""
V3.0 Layer 10 — Quality AI (15+ checks)

Extended quality scoring engine with 15 independent evaluation dimensions.
Each dimension scores 0.0 ~ 1.0 independently. Weighted total → quality grade.

Grades: A (>=0.85), B (>=0.70), C (>=0.50), F (<0.50)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ── Default thresholds ────────────────────────────────────────

QUALITY_CHECKS: Dict[str, float] = {
    "face_id": 0.8,          # Face identity consistency (CLIP comparison)
    "pose": 0.6,             # Pose naturalness (OpenPose check)
    "scene": 0.7,            # Scene matching
    "ocr": 0.9,              # Text region detection (no garbled text)
    "hand": 0.5,             # Hand quality
    "foot": 0.5,             # Foot quality
    "weapon": 0.6,           # Weapon/prop quality
    "character": 0.7,        # Character completeness
    "lighting": 0.7,         # Lighting quality
    "color": 0.7,            # Color harmony
    "noise": 0.8,            # Noise level (inverted: higher = less noise)
    "blur": 0.8,             # Sharpness (inverted: higher = sharper)
    "style": 0.7,            # Style consistency
    "anatomy": 0.6,          # Anatomical correctness
    "composition": 0.6,      # Composition quality
}

# Quality grade thresholds
GRADE_THRESHOLDS: Dict[str, float] = {
    "A": 0.85,
    "B": 0.70,
    "C": 0.50,
    # below 0.50 = "F"
}


@dataclass
class QualityReport:
    """Result of a quality evaluation run."""

    scores: Dict[str, float] = field(default_factory=dict)
    total_score: float = 0.0
    grade: str = "F"
    passed: bool = False
    failing_items: List[str] = field(default_factory=list)
    fix_suggestions: Dict[str, str] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        parts = [f"Grade: {self.grade} (total={self.total_score:.3f})"]
        parts.append(f"Passed: {self.passed}")
        if self.failing_items:
            parts.append(f"Failed: {', '.join(self.failing_items)}")
        return " | ".join(parts)


class QualityEngine:
    """Extended quality scoring engine.

    Evaluates 15 dimensions independently, computes weighted total,
    and generates fix suggestions for failing items.

    Usage:
        engine = QualityEngine(thresholds=QUALITY_CHECKS)
        report = engine.evaluate("path/to/image.png")
        if report.passed:
            print("Quality OK")
        else:
            for item in report.failing_items:
                print(f"Fix: {item} → {report.fix_suggestions[item]}")
    """

    def __init__(
        self,
        thresholds: Optional[Dict[str, float]] = None,
        weights: Optional[Dict[str, float]] = None,
    ):
        self.thresholds = thresholds or dict(QUALITY_CHECKS)

        # Default weights: face/character/anatomy are most important
        self.weights = weights or {
            "face_id": 1.5,
            "pose": 0.8,
            "scene": 0.8,
            "ocr": 0.5,
            "hand": 0.7,
            "foot": 0.5,
            "weapon": 0.5,
            "character": 1.2,
            "lighting": 0.8,
            "color": 0.8,
            "noise": 0.6,
            "blur": 0.8,
            "style": 0.8,
            "anatomy": 1.0,
            "composition": 0.8,
        }

    def evaluate(self, image_path: str) -> QualityReport:
        """Run all 15 quality checks and compute final grade.

        Args:
            image_path: Path to the generated image.

        Returns:
            QualityReport with scores, grade, and fix suggestions.
        """
        report = QualityReport()

        scores: Dict[str, float] = {}
        for check_name in self.thresholds:
            score = self._score_dimension(image_path, check_name)
            scores[check_name] = score

        report.scores = scores
        report.total_score = self._compute_weighted_total(scores)
        report.grade = self._compute_grade(report.total_score)
        report.failing_items = self._find_failing(scores)
        report.fix_suggestions = self._generate_fixes(report.failing_items)
        report.passed = len(report.failing_items) == 0

        return report

    # ── Scoring ────────────────────────────────────────────────

    def _score_dimension(self, image_path: str, check_name: str) -> float:
        """Score a single quality dimension.

        Stub: In production, this runs actual ML checks
        (CLIP similarity, OpenPose, OCR detection, Laplacian variance, etc.)

        Returns a float 0.0 ~ 1.0 (higher = better).
        """
        # Implementation per dimension:
        # face_id: CLIP cosine similarity with face embedding
        # pose: OpenPose joint confidence average
        # scene: CLIP similarity with scene description
        # ocr: 1.0 - (detected text area / image area)
        # hand: OpenPose hand keypoint confidence
        # foot: OpenPose foot keypoint confidence
        # weapon/prop: segmentation IOU with prop mask
        # character: segmentation completeness
        # lighting: histogram entropy
        # color: color palette harmony score
        # noise: 1.0 - std deviation of flat regions
        # blur: Laplacian variance normalized
        # style: feature distance from reference
        # anatomy: limb ratio check
        # composition: rule-of-thirds intersection score
        return 0.0

    def _compute_weighted_total(self, scores: Dict[str, float]) -> float:
        """Compute weighted average of all scores."""
        total_weight = 0.0
        weighted_sum = 0.0
        for key, score in scores.items():
            w = self.weights.get(key, 1.0)
            weighted_sum += score * w
            total_weight += w
        return weighted_sum / total_weight if total_weight > 0 else 0.0

    def _compute_grade(self, total_score: float) -> str:
        """Map total score to letter grade."""
        for grade, threshold in sorted(GRADE_THRESHOLDS.items(), key=lambda x: -x[1]):
            if total_score >= threshold:
                return grade
        return "F"

    def _find_failing(self, scores: Dict[str, float]) -> List[str]:
        """Find items that fall below their thresholds."""
        failing = []
        for check_name, threshold in self.thresholds.items():
            if scores.get(check_name, 0.0) < threshold:
                failing.append(check_name)
        return failing

    def _generate_fixes(self, failing_items: List[str]) -> Dict[str, str]:
        """Generate fix suggestions for each failing item."""
        FIX_TEMPLATES = {
            "face_id": "Increase PuLID strength or add more face reference images",
            "pose": "Add OpenPose ControlNet with reference pose skeleton",
            "scene": "Refine scene prompt with location/weather details",
            "ocr": "Add 'no text, no watermark' to negative prompt",
            "hand": "Add 'detailed hands, perfect hands' to positive prompt",
            "foot": "Add 'bare feet, detailed feet' if feet visible",
            "weapon": "Add prop reference image to prompt",
            "character": "Increase character LoRA weight or add detail to character prompt",
            "lighting": "Specify lighting direction and intensity in prompt",
            "color": "Specify color palette in prompt or apply LUT",
            "noise": "Increase sampling steps or apply denoising pass",
            "blur": "Decrease CFG or increase sharpness in prompt",
            "style": "Reinforce art_style keyword in prompt",
            "anatomy": "Enable anatomy-aware ControlNet or add negative terms",
            "composition": "Add composition keywords (rule of thirds, framing)",
        }
        return {
            item: FIX_TEMPLATES.get(item, f"Adjust {item} threshold or prompt")
            for item in failing_items
        }

    # ── Statistics ─────────────────────────────────────────────

    def batch_evaluate(
        self,
        image_paths: List[str],
    ) -> List[QualityReport]:
        """Evaluate multiple images and return reports."""
        reports = [self.evaluate(path) for path in image_paths]
        return reports

    def batch_summary(self, reports: List[QualityReport]) -> Dict:
        """Summarize batch evaluation results."""
        if not reports:
            return {}
        passing = sum(1 for r in reports if r.passed)
        grades = [r.grade for r in reports]
        avg_total = sum(r.total_score for r in reports) / len(reports)
        all_failures: Dict[str, int] = {}
        for r in reports:
            for item in r.failing_items:
                all_failures[item] = all_failures.get(item, 0) + 1
        return {
            "total_images": len(reports),
            "passing": passing,
            "failing": len(reports) - passing,
            "pass_rate": passing / len(reports),
            "average_score": avg_total,
            "grade_distribution": {g: grades.count(g) for g in set(grades)},
            "common_failures": sorted(all_failures.items(), key=lambda x: -x[1]),
        }
