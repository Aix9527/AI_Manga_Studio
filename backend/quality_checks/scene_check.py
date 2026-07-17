"""
Scene Match Check — Background vs. Description

Compares the generated background against the scene description
using CLIP similarity or heuristic color matching.

Prevents: "sunset described, but generated a daylight scene".
"""

from __future__ import annotations

import os
from typing import Any, Tuple

from loguru import logger

from backend.quality_engine import BaseCheck, CheckResult


class SceneMatchCheck(BaseCheck):
    """Verify background matches the scene/background description."""

    name = "scene_match"
    enabled = False   # off by default — CPU-intensive
    threshold = 0.50

    def run(self, shot: Any, file_path: str) -> CheckResult:
        if not os.path.isfile(file_path):
            return CheckResult(
                check_name=self.name, passed=False, score=0.0,
                reason="File not found",
            )

        background = getattr(shot, "background", "") or ""
        weather = getattr(shot, "weather", "") or ""
        time_of_day = getattr(shot, "time_of_day", "") or ""

        description_parts = [b for b in [background, weather, time_of_day] if b]
        if not description_parts:
            return CheckResult(
                check_name=self.name, passed=True, score=1.0,
                reason="No scene description — skip",
                metadata={"skipped": True},
            )

        description = ", ".join(description_parts)

        # Try CLIP
        try:
            return self._run_clip(file_path, description)
        except Exception:
            pass

        return self._run_color_heuristic(file_path, description)

    def check_prerequisites(self) -> Tuple[bool, str]:
        try:
            import clip
            return True, "CLIP available"
        except ImportError:
            return False, "CLIP not installed — using color heuristic"

    # ----------------------------------------------------------
    # CLIP
    # ----------------------------------------------------------

    def _run_clip(self, file_path: str, description: str) -> CheckResult:
        import clip
        import torch
        from PIL import Image

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model, preprocess = clip.load("ViT-B/32", device=device)

        image = preprocess(Image.open(file_path)).unsqueeze(0).to(device)
        text = clip.tokenize([
            description,
            "a completely different scene",
        ]).to(device)

        with torch.no_grad():
            image_features = model.encode_image(image)
            text_features = model.encode_text(text)
            image_features /= image_features.norm(dim=-1, keepdim=True)
            text_features /= text_features.norm(dim=-1, keepdim=True)

            similarity = (image_features @ text_features.T).cpu().numpy()
            match_score = float(similarity[0][0])

        # CLIP cosine similarity typically 0.2—0.4 for matching pairs
        score = min(1.0, max(0.0, match_score * 2.5))
        passed = score >= self.threshold

        return CheckResult(
            check_name=self.name,
            passed=passed,
            score=round(score, 3),
            reason=f"CLIP match: {match_score:.3f}" if score >= 0.5 else f"mismatch ({match_score:.3f})",
            fix_hint="Add scene description to positive prompt explicitly" if not passed else "",
            metadata={"raw_similarity": round(match_score, 3), "description": description[:80]},
        )

    # ----------------------------------------------------------
    # Color heuristic
    # ----------------------------------------------------------

    def _run_color_heuristic(self, file_path: str, description: str) -> CheckResult:
        """Simple color tone matching based on description keywords."""
        try:
            from PIL import Image
            import numpy as np

            img = Image.open(file_path).convert("RGB")
            arr = np.array(img, dtype=np.float32)
            mean_color = arr.mean(axis=(0, 1))  # [R, G, B]

            # Keyword → expected color bias
            warm_kw = ["sunset", "fire", "warm", "golden", "dusk", "evening", "autumn"]
            cool_kw = ["night", "moon", "blue", "cold", "winter", "underwater", "dark"]
            green_kw = ["forest", "garden", "park", "grass", "jungle", "meadow"]
            bright_kw = ["day", "sun", "bright", "noon", "daylight", "white"]

            desc_lower = description.lower()

            r, g, b = mean_color
            brightness = (r + g + b) / 3
            warm_score = r / max(g, 1.0)
            cool_score = b / max(r, 1.0)

            issues = []
            if any(kw in desc_lower for kw in warm_kw) and warm_score < 1.1:
                issues.append("expected warm tones")
            if any(kw in desc_lower for kw in cool_kw) and cool_score < 1.05:
                issues.append("expected cool tones")
            if any(kw in desc_lower for kw in bright_kw) and brightness < 80:
                issues.append("expected brighter scene")
            if any(kw in desc_lower for kw in ["dark", "night", "shadow"]) and brightness > 150:
                issues.append("expected darker scene")

            score = 1.0 - len(issues) * 0.25
            score = max(0.0, score)
            passed = score >= self.threshold

            return CheckResult(
                check_name=self.name,
                passed=passed,
                score=round(score, 3),
                reason=" | ".join(issues) if issues else f"color match OK (R={r:.0f} G={g:.0f} B={b:.0f})",
                fix_hint="Add weather/time_of_day to prompt" if not passed else "",
                metadata={
                    "mean_rgb": [round(r, 1), round(g, 1), round(b, 1)],
                    "brightness": round(brightness, 1),
                    "warm_ratio": round(warm_score, 3),
                    "cool_ratio": round(cool_score, 3),
                },
            )

        except Exception as e:
            return CheckResult(
                check_name=self.name, passed=False, score=0.0,
                reason=f"Heuristic error: {e}",
            )
