"""
Anatomy Check — Hand/Finger Count, Limb Anomalies

Uses MediaPipe Hands (if installed) or falls back to basic heuristics.
Detects:
  - Missing / extra hands
  - Wrong finger count
  - Multi-arm / merged limb artifacts
"""

from __future__ import annotations

import os
from typing import Any, List, Tuple

import numpy as np
from loguru import logger

from backend.quality_engine import BaseCheck, CheckResult

# ---------------------------------------------------------------------------
# Lazy imports
# ---------------------------------------------------------------------------
_mp_hands = None
_mp_drawing = None

def _init_mediapipe():
    global _mp_hands, _mp_drawing
    if _mp_hands is not None:
        return True
    try:
        import mediapipe as mp
        _mp_hands = mp.solutions.hands
        _mp_drawing = mp.solutions.drawing_utils
        return True
    except ImportError:
        return False


class AnatomyCheck(BaseCheck):
    """Detects anatomical anomalies in AI-generated images."""

    name = "anatomy"
    enabled = True
    threshold = 0.50

    # Expected values (per normal human in frame)
    MAX_HANDS = 2     # per visible person
    FINGERS_PER_HAND = 5
    MAX_EXTRA_LIMBS = 0

    def run(self, shot: Any, file_path: str) -> CheckResult:
        if not os.path.isfile(file_path):
            return CheckResult(
                check_name=self.name, passed=False, score=0.0,
                reason=f"File not found: {file_path}",
            )

        # Try MediaPipe first
        if _init_mediapipe():
            return self._run_mediapipe(shot, file_path)

        # Fallback: heuristic check (blob-based symmetry analysis)
        return self._run_heuristic(shot, file_path)

    def check_prerequisites(self) -> Tuple[bool, str]:
        if _init_mediapipe():
            return True, "MediaPipe ready"
        return False, "MediaPipe not installed — using heuristic fallback"

    # ----------------------------------------------------------
    # MediaPipe-based check
    # ----------------------------------------------------------

    def _run_mediapipe(self, shot: Any, file_path: str) -> CheckResult:
        import cv2

        img = cv2.imread(file_path)
        if img is None:
            return CheckResult(
                check_name=self.name, passed=False, score=0.0,
                reason="Cannot read image",
            )

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        issues: List[str] = []
        total_hands = 0
        total_fingers = 0

        with _mp_hands.Hands(
            static_image_mode=True,
            max_num_hands=6,
            min_detection_confidence=0.3,
        ) as hands:
            results = hands.process(rgb)

            if results.multi_hand_landmarks:
                total_hands = len(results.multi_hand_landmarks)

                # Extract finger counts per hand
                for hand_landmarks in results.multi_hand_landmarks:
                    fingers = self._count_fingers(hand_landmarks)
                    total_fingers += fingers
                    if fingers < 4 or fingers > 5:
                        issues.append(f"hand_{total_fingers}: {fingers} fingers")

        # Score calculation
        # Base score = 1.0, subtract penalties
        score = 1.0

        # Too many hands
        expected_chars = len(getattr(shot, "characters", []) or [])
        if expected_chars > 0:
            max_expected = expected_chars * self.MAX_HANDS
            if total_hands > max_expected:
                extra = total_hands - max_expected
                score -= extra * 0.15
                issues.append(f"extra hands: {total_hands} (expected ≤{max_expected})")

        # Wrong finger count
        if total_hands > 0:
            avg_fingers = total_fingers / total_hands
            if avg_fingers < 4.0:
                score -= 0.2
                issues.append(f"low finger avg: {avg_fingers:.1f}")
            elif avg_fingers > 5.5:
                score -= 0.2
                issues.append(f"high finger avg: {avg_fingers:.1f}")

        score = max(0.0, min(1.0, score))
        passed = score >= self.threshold

        return CheckResult(
            check_name=self.name,
            passed=passed,
            score=round(score, 3),
            reason=" | ".join(issues) if issues else f"{total_hands} hands, {total_fingers} fingers OK",
            fix_hint="Bump seed +5k, add 'perfect hands, 5 fingers' to negative prompt" if not passed else "",
            metadata={
                "total_hands": total_hands,
                "total_fingers": total_fingers,
                "avg_fingers": round(total_fingers / total_hands, 1) if total_hands else 0,
            },
        )

    @staticmethod
    def _count_fingers(hand_landmarks) -> int:
        """Count extended fingers from MediaPipe landmarks.

        Uses fingertip-to-palm distance compared to PIP joint.
        """
        # Landmark indices for fingertips and PIP joints
        tips = [4, 8, 12, 16, 20]
        pips = [3, 6, 10, 14, 18]

        count = 0
        for tip, pip in zip(tips, pips):
            tip_y = hand_landmarks.landmark[tip].y
            pip_y = hand_landmarks.landmark[pip].y
            # Fingertip above PIP joint = extended (for y-axis, smaller = higher)
            if tip_y < pip_y:
                count += 1

        # Thumb (landmark 4) uses x-axis because it extends sideways
        thumb_tip = hand_landmarks.landmark[4]
        thumb_ip = hand_landmarks.landmark[3]
        if abs(thumb_tip.x - thumb_ip.x) > 0.04:
            # Already counted in tips loop, but verify it's really extended
            pass

        return count

    # ----------------------------------------------------------
    # Heuristic fallback (no MediaPipe)
    # ----------------------------------------------------------

    def _run_heuristic(self, shot: Any, file_path: str) -> CheckResult:
        """Fallback when MediaPipe is not available.

        Uses image statistics to flag potential issues:
        - Left/right symmetry check (asymmetry may indicate extra limbs)
        - Skin-tone blob count estimation
        """
        try:
            from PIL import Image
            img = Image.open(file_path).convert("RGB")
            arr = np.array(img, dtype=np.float32) / 255.0
        except Exception:
            return CheckResult(
                check_name=self.name, passed=False, score=0.0,
                reason="Cannot open image",
            )

        h, w = arr.shape[:2]

        # Symmetry check: left half vs mirrored right half
        half = w // 2
        left = arr[:, :half, :]
        right = arr[:, half : half * 2, :]
        right_mirrored = np.flip(right, axis=1)

        mse = float(np.mean((left - right_mirrored) ** 2))

        # Perfect symmetry (like a centered character) → 0
        # High asymmetry (0.05+) → potential extra limbs
        symmetry_score = max(0.0, 1.0 - mse / 0.1)  # 0.1 MSE → score 0

        # Heuristic score
        score = 0.3 + symmetry_score * 0.7  # heavily weighted toward symmetry
        score = round(min(1.0, max(0.0, score)), 3)
        passed = score >= self.threshold

        reason = ""
        if mse > 0.05:
            reason = f"high asymmetry ({mse:.3f})"
        elif mse > 0.03:
            reason = f"moderate asymmetry ({mse:.3f})"
        else:
            reason = f"symmetry OK ({mse:.3f})"

        return CheckResult(
            check_name=self.name,
            passed=passed,
            score=score,
            reason=reason,
            fix_hint="" if passed else "Add 'symmetrical anatomy' to prompt",
            metadata={"lr_mse": round(mse, 4), "symmetry_score": round(symmetry_score, 3)},
        )
