"""
Quality Score — Sprint 7.1 Vision Critic.
Multi-dimensional quality assessment for generated manga panels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from backend.vision.image_analyzer import ImageProfile


@dataclass
class QualityReport:
    """Multi-dimensional quality assessment for a single generated panel."""
    image_path: str = ""
    shot_id: str = ""
    overall_score: float = 0.0            # 0.0–1.0 overall quality

    # Sub-scores (0.0–1.0)
    composition_score: float = 0.0         # framing, rule of thirds, depth
    style_consistency: float = 0.0         # matches target art style
    character_consistency: float = 0.0     # character looks consistent with reference
    expression_match: float = 0.0          # expression matches intent
    camera_match: float = 0.0              # camera angle matches shot spec
    technical_quality: float = 0.0         # sharpness, exposure, artifacts

    # Pass/fail
    passed: bool = False
    threshold: float = 0.65

    # Issues found
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    # Raw
    profile: Optional[ImageProfile] = None


class QualityScorer:
    """
    Multi-dimensional quality scorer.

    Takes ImageProfile + shot specifications and produces
    a comprehensive QualityReport with actionable feedback.
    """

    def __init__(self, pass_threshold: float = 0.65):
        self.threshold = pass_threshold

    def score(
        self,
        profile: ImageProfile,
        shot_spec: dict | None = None,
        reference_profile: Optional[ImageProfile] = None,
        character_reference_tags: list[str] | None = None,
    ) -> QualityReport:
        """
        Score a generated panel against specifications.

        Parameters
        ----------
        profile : ImageProfile
            Analysis of the generated image.
        shot_spec : dict, optional
            {shot_type, camera_angle, emotion, action, character_ids}
        reference_profile : ImageProfile, optional
            Analysis of a reference image for consistency comparison.
        character_reference_tags : list[str], optional
            Tags that should be present for this character.
        """
        report = QualityReport(
            image_path=profile.image_path,
            shot_id=shot_spec.get("shot_id", "") if shot_spec else "",
            profile=profile,
        )

        shot_spec = shot_spec or {}

        # Dimension 1: Composition
        report.composition_score = self._score_composition(profile, shot_spec)

        # Dimension 2: Style consistency
        report.style_consistency = self._score_style(profile, reference_profile)

        # Dimension 3: Character consistency
        report.character_consistency = self._score_character(
            profile, character_reference_tags
        )

        # Dimension 4: Expression match
        report.expression_match = self._score_expression(profile, shot_spec)

        # Dimension 5: Camera match
        report.camera_match = self._score_camera(profile, shot_spec)

        # Dimension 6: Technical quality
        report.technical_quality = self._score_technical(profile)

        # Aggregate overall
        weights = {
            "composition": 0.20,
            "style": 0.20,
            "character": 0.25,
            "expression": 0.15,
            "camera": 0.10,
            "technical": 0.10,
        }

        report.overall_score = round(
            report.composition_score * weights["composition"]
            + report.style_consistency * weights["style"]
            + report.character_consistency * weights["character"]
            + report.expression_match * weights["expression"]
            + report.camera_match * weights["camera"]
            + report.technical_quality * weights["technical"],
            4,
        )

        report.passed = report.overall_score >= self.threshold

        # Generate issues and suggestions
        self._diagnose(report, shot_spec)

        return report

    def batch_score(
        self,
        profiles: list[ImageProfile],
        shot_specs: list[dict],
        references: dict[str, ImageProfile] | None = None,
    ) -> list[QualityReport]:
        """Score a batch of generated panels."""
        reports = []
        for i, profile in enumerate(profiles):
            spec = shot_specs[i] if i < len(shot_specs) else {}
            ref_profile = None
            if references and spec.get("character_ids"):
                for cid in spec["character_ids"]:
                    if cid in references:
                        ref_profile = references[cid]
                        break
            reports.append(self.score(profile, spec, ref_profile))
        return reports

    # ── Sub-scorers ─────────────────────────────────────────────

    def _score_composition(self, profile: ImageProfile, spec: dict) -> float:
        score = 0.5  # baseline

        # Rule of thirds
        score += profile.rule_of_thirds * 0.3

        # Composition type match
        shot_type = spec.get("shot_type", "")
        if shot_type and profile.composition_type != "unknown":
            type_map = {
                "close-up": "close-up",
                "extreme-close-up": "close-up",
                "medium": "medium",
                "full-shot": "wide",
                "long-shot": "wide",
            }
            expected = type_map.get(shot_type, shot_type)
            if profile.composition_type == expected:
                score += 0.2

        return min(score, 1.0)

    def _score_style(self, profile: ImageProfile, reference: ImageProfile | None) -> float:
        if reference is None:
            # No reference — check if style tags are present
            has_style = any("manga" in t or "anime" in t or "painterly" in t for t in profile.content_tags)
            return 0.7 if has_style else 0.5

        # Compare tag overlap with reference
        if not reference.content_tags:
            return 0.5

        ref_set = set(reference.content_tags)
        profile_set = set(profile.content_tags)
        if not ref_set:
            return 0.5

        overlap = len(profile_set & ref_set)
        return min(overlap / len(ref_set), 1.0)

    def _score_character(self, profile: ImageProfile, ref_tags: list[str] | None) -> float:
        if not ref_tags:
            # Check if any character is detected
            return 0.6 if profile.character_count > 0 or profile.faces_detected > 0 else 0.3

        ref_set = set(ref_tags)
        profile_set = set(profile.content_tags)

        if not ref_set:
            return 0.5

        overlap = len(profile_set & ref_set)
        return min(overlap / len(ref_set), 1.0)

    def _score_expression(self, profile: ImageProfile, spec: dict) -> float:
        emotion = spec.get("emotion", "")
        if not emotion:
            return 0.6  # no requirement → neutral score

        emotion_map = {
            "happy": ["happy", "smiling", "joyful"],
            "sad": ["sad", "crying", "melancholy"],
            "angry": ["angry", "furious", "rage"],
            "surprised": ["surprised", "shocked"],
            "neutral": ["neutral", "calm", "serene"],
            "tense": ["tense", "nervous", "anxious"],
            "dramatic": ["dramatic", "intense"],
            "dark": ["dark", "sinister", "ominous"],
        }

        expected = set(emotion_map.get(emotion.lower(), [emotion.lower()]))
        profile_set = set(t.lower() for t in profile.content_tags)

        if not expected:
            return 0.5

        overlap = len(profile_set & expected)
        return min(overlap / max(len(expected), 1), 1.0)

    def _score_camera(self, profile: ImageProfile, spec: dict) -> float:
        camera = spec.get("camera_angle", "")
        if not camera:
            return 0.6

        camera_tags = {
            "low-angle": ["dutch angle", "dramatic"],
            "high-angle": ["overhead shot", "wide shot"],
            "eye-level": ["medium shot", "portrait"],
            "dutch": ["dutch angle"],
            "overhead": ["overhead shot"],
            "wide": ["wide shot"],
        }

        expected = set(camera_tags.get(camera.lower(), [camera.lower()]))
        profile_set = set(t.lower() for t in profile.content_tags)

        if not expected:
            return 0.5

        overlap = len(profile_set & expected)
        return min(overlap / max(len(expected), 1), 1.0)

    def _score_technical(self, profile: ImageProfile) -> float:
        score = 0.4
        score += profile.sharpness * 0.3
        score += profile.color_harmony * 0.2
        if profile.exposure == "normal":
            score += 0.1
        return min(score, 1.0)

    # ── Diagnosis ───────────────────────────────────────────────

    def _diagnose(self, report: QualityReport, spec: dict):
        """Generate human-readable issues and suggestions."""

        if report.composition_score < self.threshold:
            report.issues.append(f"Composition score {report.composition_score:.2f} — below threshold")
            report.suggestions.append("Adjust framing to better follow rule of thirds")

        if report.style_consistency < self.threshold:
            report.issues.append(f"Style consistency {report.style_consistency:.2f} below threshold")
            report.suggestions.append("Strengthen art style tags in prompt")

        if report.character_consistency < self.threshold:
            report.issues.append(f"Character consistency {report.character_consistency:.2f} below threshold")
            report.suggestions.append("Add character reference description to prompt")

        if report.expression_match < self.threshold and spec.get("emotion"):
            report.issues.append(f"Expression mismatch (expected: {spec['emotion']})")
            report.suggestions.append(f"Emphasize '{spec['emotion']}' expression in prompt")

        if report.camera_match < self.threshold and spec.get("camera_angle"):
            report.issues.append(f"Camera angle mismatch (expected: {spec['camera_angle']})")
            report.suggestions.append(f"Add '{spec['camera_angle']}' camera direction to prompt")

        if report.technical_quality < self.threshold:
            report.issues.append(f"Technical quality {report.technical_quality:.2f} below threshold")
            if report.profile and report.profile.sharpness < 0.3:
                report.suggestions.append("Image is blurry — increase steps or use upscaler")
            if report.profile and report.profile.exposure != "normal":
                report.suggestions.append(f"Exposure is {report.profile.exposure} — adjust lighting prompt")

    def summary(self, reports: list[QualityReport]) -> dict:
        """Batch summary statistics."""
        if not reports:
            return {"total": 0, "passed": 0, "mean_score": 0.0}

        passed = sum(1 for r in reports if r.passed)
        scores = [r.overall_score for r in reports]
        return {
            "total": len(reports),
            "passed": passed,
            "failed": len(reports) - passed,
            "pass_rate": round(passed / len(reports), 3),
            "mean_score": round(sum(scores) / len(scores), 4),
            "min_score": round(min(scores), 4),
            "max_score": round(max(scores), 4),
        }
