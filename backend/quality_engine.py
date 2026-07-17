"""
Quality Engine — Independent Quality Detection Layer

Runs ENTIRELY outside ComfyUI on the Python side.
After each generation, the engine evaluates output against quality criteria.
Failed shots are automatically re-queued with varied parameters — zero human intervention.

Architecture:
  generate → evaluate → (pass) → continue
                      → (fail)  → mutate seed/CFG → re-generate → evaluate → ...
                      → (fail after max_retries) → flag human review

Checks:
  face_consistency  —  same person across shots? no face swapping?
  anatomy           —  correct hand/finger count? no extra limbs?
  character_presence — is the required character in the frame?
  scene_match       —  does background match the scene description?
  image_quality     —  blur detection, contrast, AI artifacts
  flicker_temporal  —  video frame-to-frame consistency

Usage:
  engine = QualityEngine()
  result = engine.evaluate(shot, file_path)
  if result.passed:
      continue
  else:
      re-queue with mutated params
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


# ============================================================
# Data Models
# ============================================================

@dataclass
class CheckResult:
    """Single quality check result."""
    check_name: str
    passed: bool
    score: float           # 0.0 (worst) — 1.0 (perfect)
    reason: str = ""
    fix_hint: str = ""     # suggestion to improve on retry
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        status = "✓" if self.passed else "✗"
        return f"{status} {self.check_name}: {self.score:.2f} — {self.reason or 'OK'}"


@dataclass
class QualityResult:
    """Aggregated quality evaluation result."""
    shot_id: str = ""
    passed: bool = False
    overall_score: float = 0.0   # mean of individual scores
    checks: List[CheckResult] = field(default_factory=list)
    failed_checks: List[str] = field(default_factory=list)
    evaluated_at: float = 0.0
    file_path: str = ""

    @property
    def failure_summary(self) -> str:
        if self.passed:
            return "ALL PASS"
        return ", ".join(
            f"{c.check_name}({c.score:.2f})" for c in self.checks if not c.passed
        )

    def __repr__(self) -> str:
        return f"QualityResult({self.shot_id}): {self.overall_score:.2f} — {'PASS' if self.passed else 'FAIL: ' + self.failure_summary}"


# ============================================================
# V3.5: Quality Report (Diagnosis + Feedback + Regeneration)
# ============================================================

@dataclass
class IssueDiagnosis:
    """Single issue found during quality evaluation.

    Carries severity, type, description, and a concrete suggestion
    for regeneration.
    """
    severity: str            # "critical", "major", "minor", "info"
    issue_type: str          # "character_consistency", "scene_coherence",
                             # "composition_quality", "banned_word", etc.
    description: str         # Human-readable description
    suggestion: str          # Concrete fix suggestion for Prompt Engine
    affected_fields: List[str] = field(default_factory=list)
                             # Which PromptV35 fields to modify


@dataclass
class QualityReport:
    """V3.5 quality report: diagnosis + feedback + regeneration.

    Upgraded from simple scoring to actionable feedback that the
    Prompt Engine can consume to regenerate improved output.
    """
    shot_id: str = ""
    score: float = 0.0            # 0.0 ~ 1.0
    passed: bool = False
    issues: List[IssueDiagnosis] = field(default_factory=list)
    regeneration_hints: Dict[str, str] = field(default_factory=dict)
    # Summary stats
    critical_count: int = 0
    major_count: int = 0
    minor_count: int = 0

    @property
    def failure_summary(self) -> str:
        if self.passed:
            return "ALL PASS"
        return f"{self.critical_count}C/{self.major_count}M/{self.minor_count}m"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "score": self.score,
            "passed": self.passed,
            "critical_count": self.critical_count,
            "major_count": self.major_count,
            "minor_count": self.minor_count,
            "issues": [
                {
                    "severity": i.severity,
                    "type": i.issue_type,
                    "description": i.description,
                    "suggestion": i.suggestion,
                    "affected_fields": i.affected_fields,
                }
                for i in self.issues
            ],
            "regeneration_hints": self.regeneration_hints,
        }


# ============================================================
# Quality Check Base Class
# ============================================================

class BaseCheck:
    """ABC for a single quality check.

    Each check is stateless and can be enabled/disabled via config.
    GPU-agnostic: runs on CPU where possible; ML models are lazy-loaded.
    """

    name: str = "base"
    enabled: bool = True
    threshold: float = 0.5       # score below this = FAIL

    def run(self, shot: Any, file_path: str) -> CheckResult:
        """Execute this check.

        Args:
            shot: UnifiedShot with prompt/character/scene metadata.
            file_path: Path to the generated image or video.

        Returns:
            CheckResult with pass/fail decision.
        """
        raise NotImplementedError

    def check_prerequisites(self) -> Tuple[bool, str]:
        """Verify dependencies are available.

        Returns:
            (ok, error_message).
        """
        return True, ""

    def __repr__(self) -> str:
        return f"Check({self.name}, enabled={self.enabled}, thresh={self.threshold})"


# ============================================================
# Mutation Strategy
# ============================================================

@dataclass
class MutationHint:
    """Parameter mutations to apply before retrying a failed generation."""
    seed_bump: int = 0          # + to seed
    cfg_adjust: float = 0.0     # + to CFG scale (±)
    steps_add: int = 0          # + to steps
    sampler_switch: str = ""    # switch sampler if current one fails repeatedly

    def apply(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """Apply mutations to a workflow dict, returning a new copy."""
        mutated = dict(workflow)
        if self.seed_bump:
            mutated["seed"] = workflow.get("seed", 0) + self.seed_bump
        if self.cfg_adjust:
            mutated["cfg"] = round(workflow.get("cfg", 7.0) + self.cfg_adjust, 1)
        if self.steps_add:
            mutated["steps"] = min(workflow.get("steps", 30) + self.steps_add, 100)
        if self.sampler_switch:
            mutated["sampler"] = self.sampler_switch
        return mutated

    @classmethod
    def from_failures(cls, failures: List[CheckResult], retry_num: int) -> "MutationHint":
        """Generate mutation hints based on what failed and retry count.

        Args:
            failures: List of failed check results.
            retry_num: Current retry attempt number (0-based).

        Returns:
            MutationHint suggesting parameter changes.
        """
        hint = cls()
        failure_names = {f.check_name for f in failures}

        # Always bump seed on retry
        hint.seed_bump = random.randint(100, 100000)

        if "anatomy" in failure_names:
            # Anatomy issues → more negative prompt guidance + more steps
            hint.steps_add = 5 + retry_num * 5
            hint.cfg_adjust = 0.5

        if "image_quality" in failure_names:
            hint.steps_add = 10 + retry_num * 5
            hint.cfg_adjust = 0.3

        if "face_consistency" in failure_names:
            hint.cfg_adjust = 0.5

        if retry_num >= 2:
            # Aggressive mutation: switch sampler
            hint.sampler_switch = random.choice(["dpmpp_2m", "uni_pc", "dpm_2"])

        return hint


# ============================================================
# Quality Engine
# ============================================================

class QualityEngine:
    """Runs quality checks on generated outputs and manages retry logic.

    Pluggable: add new checks by subclassing BaseCheck and registering them.
    """

    def __init__(self) -> None:
        from backend.config import get_config

        cfg = get_config()
        qc = cfg.quality_engine if hasattr(cfg, "quality_engine") else {}

        self.enabled: bool = getattr(qc, "enabled", True)
        self.max_retries: int = getattr(qc, "max_retries", 3)
        self.score_threshold: float = getattr(qc, "score_threshold", 0.7)

        self._checks: List[BaseCheck] = []
        self._load_checks(getattr(qc, "checks", {}))

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def evaluate(self, shot: Any, file_path: str) -> QualityResult:
        """Run all enabled checks on a generated file.

        Args:
            shot: UnifiedShot with metadata.
            file_path: Path to generated image or video.

        Returns:
            QualityResult with overall pass/fail.
        """
        result = QualityResult(
            shot_id=shot.shot_id if hasattr(shot, "shot_id") else "",
            evaluated_at=time.time(),
            file_path=file_path,
        )

        if not self.enabled or not self._checks:
            result.passed = True
            result.overall_score = 1.0
            logger.debug("QualityEngine: Disabled or no checks → auto-pass")
            return result

        scores = []
        for check in self._checks:
            if not check.enabled:
                continue

            try:
                cr = check.run(shot, file_path)
                result.checks.append(cr)
                scores.append(cr.score)

                if not cr.passed:
                    result.failed_checks.append(cr.check_name)
            except Exception as e:
                logger.warning(f"QualityEngine: Check '{check.name}' threw: {e}")
                # Degrade gracefully: failed check = pass with low score
                cr = CheckResult(
                    check_name=check.name,
                    passed=False,
                    score=0.0,
                    reason=f"Check error: {e}",
                )
                result.checks.append(cr)
                result.failed_checks.append(check.name)

        # Decision
        result.overall_score = sum(scores) / len(scores) if scores else 0.0
        result.passed = (
            result.overall_score >= self.score_threshold
            and len(result.failed_checks) == 0
        )

        # Log
        status = "PASS" if result.passed else "FAIL"
        logger.info(
            f"QualityEngine: {status} | {result.shot_id} | "
            f"score={result.overall_score:.2f} "
            + (f"→ {result.failure_summary}" if not result.passed else "")
        )

        return result

    def retry_with_quality(
        self,
        shot: Any,
        generate_fn,
        workflow: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, QualityResult]:
        """Generate and retry until quality passes or max_retries exhausted.

        Args:
            shot: The shot to generate.
            generate_fn: Callable that takes (shot, workflow) and returns (file_path, workflow_dict).
            workflow: Optional initial workflow dict.

        Returns:
            (best_file_path, final_quality_result).
            File path may be from a failed generation if max_retries hit.
        """
        best_path = ""
        best_score = -1.0
        best_result: Optional[QualityResult] = None
        current_workflow = workflow

        for attempt in range(self.max_retries + 1):
            # Generate
            file_path, used_workflow = generate_fn(shot, current_workflow)

            # Evaluate
            result = self.evaluate(shot, file_path)

            if result.overall_score > best_score:
                best_score = result.overall_score
                best_path = file_path
                best_result = result

            if result.passed:
                logger.info(f"QualityEngine: PASS on attempt {attempt + 1}/{self.max_retries + 1}")
                return best_path, result

            logger.warning(
                f"QualityEngine: FAIL attempt {attempt + 1}/{self.max_retries + 1} "
                f"({result.failure_summary})"
            )

            # Mutate and retry
            if attempt < self.max_retries:
                hint = MutationHint.from_failures(
                    [c for c in result.checks if not c.passed], attempt
                )
                current_workflow = hint.apply(used_workflow)
                logger.info(
                    f"QualityEngine: Retrying — seed→{current_workflow.get('seed')}, "
                    f"CFG→{current_workflow.get('cfg')}, steps→{current_workflow.get('steps')}"
                )

        # Max retries exhausted — return best result
        logger.error(
            f"QualityEngine: Max retries ({self.max_retries}) exhausted for {shot.shot_id}. "
            f"Best score: {best_score:.2f}"
        )
        return best_path, best_result or QualityResult(shot_id=shot.shot_id, passed=False)

    # ----------------------------------------------------------
    # Check Registry
    # ----------------------------------------------------------

    def _load_checks(self, check_configs: Dict[str, Dict[str, Any]]) -> None:
        """Load checks from config with per-check thresholds."""
        checks: List[BaseCheck] = []

        # --- Image Quality (no ML deps, always safe) ---
        try:
            from backend.quality_checks.image_quality import ImageQualityCheck
            checks.append(ImageQualityCheck())
        except ImportError as e:
            logger.debug(f"QualityEngine: image_quality check not available: {e}")

        # --- Anatomy ---
        try:
            from backend.quality_checks.anatomy import AnatomyCheck
            checks.append(AnatomyCheck())
        except ImportError as e:
            logger.debug(f"QualityEngine: anatomy check not available: {e}")

        # --- Face Consistency ---
        try:
            from backend.quality_checks.face_check import FaceConsistencyCheck
            checks.append(FaceConsistencyCheck())
        except ImportError as e:
            logger.debug(f"QualityEngine: face_consistency check not available: {e}")

        # --- Character Presence ---
        try:
            from backend.quality_checks.character_check import CharacterPresenceCheck
            checks.append(CharacterPresenceCheck())
        except ImportError as e:
            logger.debug(f"QualityEngine: character_presence check not available: {e}")

        # --- Scene Match ---
        try:
            from backend.quality_checks.scene_check import SceneMatchCheck
            checks.append(SceneMatchCheck())
        except ImportError as e:
            logger.debug(f"QualityEngine: scene_match check not available: {e}")

        # Apply per-check config overrides
        for check in checks:
            cfg = check_configs.get(check.name, {})
            if "enabled" in cfg:
                check.enabled = cfg["enabled"]
            if "threshold" in cfg:
                check.threshold = cfg["threshold"]

        self._checks = checks

        if checks:
            logger.info(f"QualityEngine: Loaded {len(checks)} checks — "
                        f"{', '.join(c.name for c in checks)}")

    @property
    def checks(self) -> List[BaseCheck]:
        return self._checks

    # ----------------------------------------------------------
    # V3.5: Diagnosis + Regeneration
    # ----------------------------------------------------------

    def diagnose(self, shot: Any, file_path: str) -> QualityReport:
        """Run all checks and produce a QualityReport with regeneration hints.

        V3.5 upgrade: replaces simple pass/fail with actionable diagnosis.

        Args:
            shot: UnifiedShot with metadata.
            file_path: Path to generated image or video.

        Returns:
            QualityReport with score, issues list, and regeneration_hints.
        """
        result = self.evaluate(shot, file_path)
        report = QualityReport(
            shot_id=result.shot_id,
            score=result.overall_score,
            passed=result.passed,
        )

        # Convert CheckResult failures to IssueDiagnosis
        for check in result.checks:
            if check.passed:
                continue
            severity = self._map_severity(check.check_name, check.score)
            issue = IssueDiagnosis(
                severity=severity,
                issue_type=check.check_name,
                description=check.reason or f"{check.check_name} score={check.score:.2f}",
                suggestion=check.fix_hint or self._default_suggestion(check.check_name),
                affected_fields=self._affected_fields(check.check_name),
            )
            report.issues.append(issue)

        # Tally severity counts
        for issue in report.issues:
            if issue.severity == "critical":
                report.critical_count += 1
            elif issue.severity == "major":
                report.major_count += 1
            else:
                report.minor_count += 1

        # Build regeneration hints
        report.regeneration_hints = self._build_regeneration_hints(report.issues)

        return report

    def generate_regeneration_prompt(
        self, shot: Any, issues: List[IssueDiagnosis]
    ) -> Dict[str, str]:
        """Generate a repair prompt for the Prompt Engine.

        Analyzes failed diagnostics and produces field-specific
        corrections that the Prompt Engine can inject into PromptV35.

        Args:
            shot: The failed shot.
            issues: List of diagnosed issues.

        Returns:
            Dict mapping PromptV35 field names → correction strings.
        """
        corrections: Dict[str, str] = {}

        for issue in issues:
            if issue.issue_type == "character_consistency":
                corrections["character_prompt"] = (
                    corrections.get("character_prompt", "")
                    + f"[FIX: {issue.suggestion}] "
                )
            elif issue.issue_type == "scene_coherence":
                corrections["scene_prompt"] = (
                    corrections.get("scene_prompt", "")
                    + f"[FIX: {issue.suggestion}] "
                )
            elif issue.issue_type == "composition_quality":
                corrections["camera_prompt"] = (
                    corrections.get("camera_prompt", "")
                    + f"[FIX: {issue.suggestion}] "
                )
            elif issue.issue_type == "banned_word":
                corrections["negative_prompt"] = (
                    corrections.get("negative_prompt", "")
                    + f"[FILTER: {issue.suggestion}] "
                )
            elif issue.issue_type == "image_quality":
                corrections["lighting_prompt"] = (
                    corrections.get("lighting_prompt", "")
                    + f"[ENHANCE: {issue.suggestion}] "
                )
            elif issue.issue_type in ("scene_match", "character_presence"):
                corrections["scene_prompt"] = (
                    corrections.get("scene_prompt", "")
                    + f"[ADJUST: {issue.suggestion}] "
                )

        logger.debug(
            f"QualityEngine: Generated regeneration hints for {len(issues)} issues → "
            f"{list(corrections.keys())}"
        )
        return corrections

    def _map_severity(self, check_name: str, score: float) -> str:
        """Map check name + score to severity level."""
        critical_checks = {"face_consistency", "character_presence", "banned_word"}
        major_checks = {"anatomy", "scene_match", "scene_coherence"}
        if check_name in critical_checks or score < 0.3:
            return "critical"
        elif check_name in major_checks or score < 0.5:
            return "major"
        return "minor"

    def _default_suggestion(self, check_name: str) -> str:
        """Default fix suggestion per check type."""
        suggestions = {
            "face_consistency": "Increase face ID weight or re-run with PuLID",
            "anatomy": "Add negative prompt for malformed hands and extra limbs",
            "character_presence": "Ensure character reference image is included in prompt",
            "scene_match": "Verify scene description matches shot context",
            "image_quality": "Increase steps and reduce CFG scale for cleaner output",
            "flicker_temporal": "Enable optical flow consistency check",
            "banned_word": "Replace prohibited terms with safe alternatives",
            "character_consistency": "Re-run with same seed and face ID",
            "scene_coherence": "Ensure background matches scene DNA description",
            "composition_quality": "Adjust camera framing and remove clutter",
        }
        return suggestions.get(check_name, "Re-generate with varied parameters")

    def _affected_fields(self, check_name: str) -> List[str]:
        """Map check name to affected PromptV35 fields."""
        field_map: Dict[str, List[str]] = {
            "face_consistency": ["character_prompt"],
            "anatomy": ["negative_prompt"],
            "character_presence": ["character_prompt"],
            "scene_match": ["scene_prompt"],
            "image_quality": ["lighting_prompt", "negative_prompt"],
            "flicker_temporal": ["motion_prompt"],
            "banned_word": ["negative_prompt"],
            "character_consistency": ["character_prompt"],
            "scene_coherence": ["scene_prompt"],
            "composition_quality": ["camera_prompt"],
        }
        return field_map.get(check_name, [])

    def _build_regeneration_hints(
        self, issues: List[IssueDiagnosis]
    ) -> Dict[str, str]:
        """Build a hints dict for Prompt Engine regeneration."""
        hints: Dict[str, str] = {}
        for issue in issues:
            for field in issue.affected_fields:
                hints[field] = (
                    hints.get(field, "") + f"{issue.suggestion}; "
                )
        # Trim trailing "; "
        return {k: v.rstrip("; ") for k, v in hints.items()}

    def prerequisite_report(self) -> str:
        """Check which dependencies are available."""
        lines = ["Quality Check Prerequisites:"]
        for check in self._checks:
            ok, msg = check.check_prerequisites()
            icon = "✓" if ok else "✗"
            lines.append(f"  {icon} {check.name}: {msg}")
        return "\n".join(lines)


# ----------------------------------------------------------
# Singleton
# ----------------------------------------------------------
import threading

_engine: Optional[QualityEngine] = None
_lock = threading.Lock()


def get_quality_engine() -> QualityEngine:
    """Get or create the global quality engine singleton."""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = QualityEngine()
    return _engine
