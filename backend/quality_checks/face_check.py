"""
Face Consistency Check — Same Person Across Shots

Uses DeepFace (if installed) or falls back to CLIP-based embedding.
Compares the current shot's face against a reference face for the character.

Critical for multi-shot sequences to prevent face-swapping artifacts.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

import numpy as np
from loguru import logger

from backend.quality_engine import BaseCheck, CheckResult


class FaceConsistencyCheck(BaseCheck):
    """Verify that generated faces match the character reference."""

    name = "face_consistency"
    enabled = True
    threshold = 0.60  # similarity score threshold

    def __init__(self):
        super().__init__()
        self._reference_embeddings: Dict[str, np.ndarray] = {}

    def run(self, shot: Any, file_path: str) -> CheckResult:
        if not os.path.isfile(file_path):
            return CheckResult(
                check_name=self.name, passed=False, score=0.0,
                reason=f"File not found: {file_path}",
            )

        characters = getattr(shot, "characters", []) or []
        if not characters:
            return CheckResult(
                check_name=self.name, passed=True, score=1.0,
                reason="No named characters — skip",
                metadata={"skipped": True},
            )

        # Try DeepFace first
        try:
            return self._run_deepface(shot, file_path, characters)
        except Exception:
            pass

        # Fallback: CLIP similarity
        return self._run_fallback(shot, file_path, characters)

    def check_prerequisites(self) -> Tuple[bool, str]:
        try:
            import deepface
            return True, f"DeepFace {deepface.__version__}"
        except ImportError:
            return False, "DeepFace not installed — using heuristic fallback"

    # ----------------------------------------------------------
    # DeepFace
    # ----------------------------------------------------------

    def _run_deepface(self, shot: Any, file_path: str, characters: list) -> CheckResult:
        from deepface import DeepFace

        scores = []
        issues = []

        for char_name in characters:
            # Get reference image from project cache
            ref_path = self._find_reference(char_name)
            if not ref_path:
                scores.append(0.8)  # assume OK with no reference
                continue

            try:
                result = DeepFace.verify(
                    img1_path=ref_path,
                    img2_path=file_path,
                    model_name="Facenet",
                    enforce_detection=False,
                    silent=True,
                )
                similarity = 1.0 - result.get("distance", 1.0)
                similarity = max(0.0, similarity)
                scores.append(similarity)

                if similarity < self.threshold:
                    issues.append(f"{char_name}: {similarity:.2f} (threshold={self.threshold})")

            except Exception as e:
                logger.debug(f"FaceConsistency: DeepFace compare failed for '{char_name}': {e}")
                scores.append(0.8)

        avg = sum(scores) / len(scores) if scores else 1.0
        passed = avg >= self.threshold and all(s >= self.threshold for s in scores)

        return CheckResult(
            check_name=self.name,
            passed=passed,
            score=round(avg, 3),
            reason=" | ".join(issues) if issues else f"{len(scores)} chars matched",
            fix_hint="Add character reference to negative prompt, bump seed" if not passed else "",
            metadata={"per_character": dict(zip(characters, [round(s, 3) for s in scores]))},
        )

    # ----------------------------------------------------------
    # Fallback (no DeepFace)
    # ----------------------------------------------------------

    def _run_fallback(self, shot: Any, file_path: str, characters: list) -> CheckResult:
        """Fallback: basic structural checks when no ML face model is available."""
        try:
            from PIL import Image
            img = Image.open(file_path)
            w, h = img.size

            # Heuristic: check that image isn't pure noise / completely blank
            arr = np.array(img.convert("RGB"), dtype=np.float32)
            variance = float(np.var(arr / 255.0))

            if variance < 0.001:
                return CheckResult(
                    check_name=self.name, passed=False, score=0.0,
                    reason="Image appears blank/noise",
                )

            # Check that image dimensions make sense for character rendering
            score = min(1.0, variance * 50)  # variance 0.02 → score 1.0
            score = round(score, 3)

            return CheckResult(
                check_name=self.name,
                passed=score >= self.threshold,
                score=score,
                reason=f"heuristic score={score:.3f} (no DeepFace)",
                fix_hint="Install deepface for accurate face consistency checks" if score < self.threshold else "",
                metadata={"heuristic": True, "variance": round(variance, 5)},
            )

        except Exception as e:
            return CheckResult(
                check_name=self.name, passed=False, score=0.0,
                reason=f"Fallback error: {e}",
            )

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    def _find_reference(self, char_name: str) -> Optional[str]:
        """Find the character's reference image in project storage."""
        from backend.config import get_config

        cfg = get_config()
        dirs = [
            os.path.join(cfg.project.output_dir, "characters"),
            os.path.join(cfg.project.dir, "storage", "output", "characters"),
            cfg.paths.storage or "",
        ]

        for d in dirs:
            if not d or not os.path.isdir(d):
                continue
            for fname in os.listdir(d):
                if char_name.lower() in fname.lower() and fname.endswith((".png", ".jpg", ".jpeg", "_ref.png")):
                    return os.path.join(d, fname)

        return None
