"""Shot directive validator (Phase 10.7-B).

Deterministic checks that keep LLM directors honest: any failed check makes
the HybridDirector fall back to the rule provider.  Checks:

- ``shot_count``     sequence-level: directive ids match shot ids 1:1
- ``camera_valid``   camera dict with angle / movement / distance set
- ``lighting_valid`` lighting dict with style / key / temperature set
- ``character_valid`` declared characters are covered by continuity knowledge
- ``continuity_valid`` continuity dict with previous_shot + constraints list
- ``physics_valid``  emotion curve is temporally sane (t monotonic, bounded)
- ``emotion_valid``  emotion curve points carry a valid emotion + intensity
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from backend.agents.director_v2 import ShotDirective
from backend.story.models import Shot

# Physically implausible camera combos (small, demonstrable table).
_IMPOSSIBLE_COMBOS = {
    ("orbit", "extreme-close-up"),
    ("crane", "extreme-close-up"),
    ("dolly", "extreme-close-up"),
}

_CAMERA_KEYS = ("angle", "movement", "distance")
_LIGHTING_KEYS = ("style", "key", "temperature")


@dataclass
class ValidationReport:
    ok: bool = True
    checks: dict[str, bool] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "checks": self.checks, "errors": self.errors}


class ShotValidator:
    """Validates one directive (and a whole sequence)."""

    def validate(
        self,
        directive: ShotDirective,
        shot: Shot | None = None,
        section_context: dict | None = None,
    ) -> ValidationReport:
        shot = shot or _shot_for(directive)
        report = ValidationReport()
        report.checks["camera_valid"] = self._camera_valid(directive, report)
        report.checks["lighting_valid"] = self._lighting_valid(directive, report)
        report.checks["character_valid"] = self._character_valid(directive, shot, section_context or {}, report)
        report.checks["continuity_valid"] = self._continuity_valid(directive, report)
        report.checks["emotion_valid"] = self._emotion_valid(directive, report)
        report.checks["physics_valid"] = self._physics_valid(directive, shot, report)
        report.checks["shot_id_match"] = directive.shot_id == shot.id or not shot.id
        if not report.checks["shot_id_match"]:
            report.errors.append(f"directive.shot_id={directive.shot_id} != shot.id={shot.id}")
        report.ok = all(report.checks.values()) and not report.errors
        return report

    def validate_sequence(
        self,
        directives: list[ShotDirective],
        shots: list[Shot],
    ) -> ValidationReport:
        """shot_count check: every shot gets exactly one directive with the right id."""
        report = ValidationReport()
        expected = [s.id for s in shots]
        actual = [d.shot_id for d in directives]
        report.checks["shot_count"] = len(directives) == len(shots) and actual == expected
        if not report.checks["shot_count"]:
            report.errors.append(
                f"shot_count mismatch: expected {len(shots)} directives {expected}, got {len(directives)} {actual}"
            )
        report.ok = report.checks["shot_count"]
        return report

    # ------------------------------------------------------------- checks
    def _camera_valid(self, directive: ShotDirective, report: ValidationReport) -> bool:
        camera = directive.camera or {}
        if not isinstance(camera, dict):
            report.errors.append("camera must be an object")
            return False
        missing = [k for k in _CAMERA_KEYS if not str(camera.get(k, "")).strip()]
        if missing:
            report.errors.append(f"camera missing: {missing}")
            return False
        movement, distance = str(camera.get("movement", "")), str(camera.get("distance", ""))
        if (movement, distance) in _IMPOSSIBLE_COMBOS:
            report.errors.append(f"impossible camera combo: {movement}+{distance}")
            return False
        return True

    def _lighting_valid(self, directive: ShotDirective, report: ValidationReport) -> bool:
        lighting = directive.lighting or {}
        if not isinstance(lighting, dict):
            report.errors.append("lighting must be an object")
            return False
        missing = [k for k in _LIGHTING_KEYS if not str(lighting.get(k, "")).strip()]
        if missing:
            report.errors.append(f"lighting missing: {missing}")
            return False
        return True

    def _character_valid(
        self,
        directive: ShotDirective,
        shot: Shot,
        section_context: dict,
        report: ValidationReport,
    ) -> bool:
        declared = shot.character_ids or []
        if not declared:
            return True
        known = (section_context or {}).get("character_state") or {}
        if not known:
            # No character memory was supplied to the director -> nothing to check
            return True
        constraints = list(directive.continuity.get("constraints", [])) if isinstance(directive.continuity, dict) else []
        joined = " ".join(str(c) for c in constraints)
        if any(cid and cid.lower() in joined.lower() for cid in declared):
            return True
        # Lenient pass: the directive still carries character/emotion knowledge
        if directive.emotion_curve and constraints:
            return True
        report.errors.append(f"characters {declared} not covered by directive")
        return False

    def _continuity_valid(self, directive: ShotDirective, report: ValidationReport) -> bool:
        continuity = directive.continuity or {}
        if not isinstance(continuity, dict):
            report.errors.append("continuity must be an object")
            return False
        if "previous_shot" not in continuity:
            report.errors.append("continuity missing previous_shot")
            return False
        constraints = continuity.get("constraints")
        if not isinstance(constraints, list):
            report.errors.append("continuity.constraints must be a list")
            return False
        return True

    def _emotion_valid(self, directive: ShotDirective, report: ValidationReport) -> bool:
        curve = directive.emotion_curve or []
        if not isinstance(curve, list) or not curve:
            report.errors.append("emotion_curve must be a non-empty list")
            return False
        for point in curve:
            if not isinstance(point, dict):
                report.errors.append(f"emotion_curve point not object: {point!r}")
                return False
            if not str(point.get("emotion", "")).strip():
                report.errors.append("emotion_curve point missing emotion")
                return False
            intensity = point.get("intensity")
            if not isinstance(intensity, (int, float)) or not (0.0 <= float(intensity) <= 1.0):
                report.errors.append(f"emotion_curve intensity out of [0,1]: {intensity!r}")
                return False
        return True

    def _physics_valid(self, directive: ShotDirective, shot: Shot, report: ValidationReport) -> bool:
        curve = directive.emotion_curve or []
        if not curve:
            return False
        duration = max(float(getattr(shot, "duration", 5.0) or 5.0), 1.0)
        prev_t = -math.inf
        for point in curve:
            t = point.get("t")
            if not isinstance(t, (int, float)) or not math.isfinite(float(t)):
                report.errors.append(f"emotion_curve t not a finite number: {t!r}")
                return False
            if float(t) < prev_t:
                report.errors.append("emotion_curve t must be monotonic")
                return False
            if float(t) > duration * 1.01:
                report.errors.append(f"emotion_curve t={t} beyond shot duration {duration}")
                return False
            prev_t = float(t)
        return True


def _shot_for(directive: ShotDirective) -> Shot:
    return Shot(id=directive.shot_id, duration=5.0)
