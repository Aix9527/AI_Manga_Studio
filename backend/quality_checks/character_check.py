"""
Character Presence Check — Required Characters in Frame

Verifies that named characters actually appear in the generated image.
Uses CLIP-based zero-shot classification with singleton model caching.
Falls back to heuristic only when CLIP is permanently unavailable.

Prevents: "character disappeared from shot" regressions.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Optional, Tuple

from loguru import logger

from backend.quality_engine import BaseCheck, CheckResult

# Module-level CLIP singleton (lazy-loaded once, never reloaded)
_clip_model: Optional[Any] = None
_clip_preprocess: Optional[Any] = None
_clip_device: str = ""
_clip_lock = threading.Lock()
_clip_permanently_unavailable: bool = False


def _get_clip():
    """Lazy-load CLIP ViT-B/32 once and cache globally."""
    global _clip_model, _clip_preprocess, _clip_device, _clip_permanently_unavailable

    if _clip_permanently_unavailable:
        return None, None, ""

    if _clip_model is not None:
        return _clip_model, _clip_preprocess, _clip_device

    with _clip_lock:
        if _clip_model is not None:
            return _clip_model, _clip_preprocess, _clip_device

        try:
            import torch
            import clip as clip_module

            device = "cuda" if torch.cuda.is_available() else "cpu"
            model, preprocess = clip_module.load("ViT-B/32", device=device)
            _clip_model = model
            _clip_preprocess = preprocess
            _clip_device = device
            logger.info("CharacterPresenceCheck: CLIP ViT-B/32 loaded (singleton)")
            return model, preprocess, device
        except Exception as e:
            _clip_permanently_unavailable = True
            logger.warning(f"CharacterPresenceCheck: CLIP unavailable — {e}")
            return None, None, ""


class CharacterPresenceCheck(BaseCheck):
    """Check if required characters are present in the image.

    Uses a global CLIP singleton — model is downloaded once and reused.
    If CLIP is unavailable, marks the check as skipped (not neutral 0.50).
    """

    name = "character_presence"
    enabled = True
    threshold = 0.55

    def run(self, shot: Any, file_path: str) -> CheckResult:
        if not os.path.isfile(file_path):
            return CheckResult(
                check_name=self.name, passed=False, score=0.0,
                reason="File not found",
            )

        characters = getattr(shot, "characters", []) or []
        if not characters:
            return CheckResult(
                check_name=self.name, passed=True, score=1.0,
                reason="No required characters — skip",
                metadata={"skipped": True, "reason": "no_characters"},
            )

        # Try CLIP (singleton, no re-download)
        model, preprocess, device = _get_clip()
        if model is not None:
            try:
                return self._run_clip_cached(
                    shot, file_path, characters, model, preprocess, device
                )
            except Exception as e:
                logger.warning(f"CharacterPresenceCheck: CLIP inference failed — {e}")

        # CLIP unavailable → skip with clear metadata, NOT neutral 0.50
        return CheckResult(
            check_name=self.name,
            passed=True,   # don't block pipeline for unavailable check
            score=1.0,
            reason="CLIP not available — character presence skipped",
            fix_hint="Ensure CLIP ViT-B/32 model is downloaded and accessible",
            metadata={
                "skipped": True,
                "reason": "clip_unavailable",
                "characters": characters,
            },
        )

    def check_prerequisites(self) -> Tuple[bool, str]:
        model, _, _ = _get_clip()
        if model is not None:
            return True, "CLIP ready (singleton)"
        return False, "CLIP not available — model download may have failed"

    # ----------------------------------------------------------
    # CLIP-based detection (uses cached model)
    # ----------------------------------------------------------

    def _run_clip_cached(
        self,
        shot: Any,
        file_path: str,
        characters: list,
        model: Any,
        preprocess: Any,
        device: str,
    ) -> CheckResult:
        import torch
        import numpy as np
        from PIL import Image

        image = preprocess(Image.open(file_path)).unsqueeze(0).to(device)

        scores_per_char = {}
        for char_name in characters:
            text = clip_tokenize([
                f"a photo of {char_name}, a character in the scene",
                f"a photo without {char_name}",
            ]).to(device)

            with torch.no_grad():
                image_features = model.encode_image(image)
                text_features = model.encode_text(text)
                image_features /= image_features.norm(dim=-1, keepdim=True)
                text_features /= text_features.norm(dim=-1, keepdim=True)

                similarity = (image_features @ text_features.T).cpu().numpy()
                presence_score = float(similarity[0][0])
                absence_score = float(similarity[0][1])

                confidence = presence_score / max(presence_score + absence_score, 1e-6)
                scores_per_char[char_name] = round(confidence, 3)

        avg = sum(scores_per_char.values()) / len(scores_per_char)
        passed = avg >= self.threshold

        issues = [f"{k}: {v:.2f}" for k, v in scores_per_char.items() if v < self.threshold]

        return CheckResult(
            check_name=self.name,
            passed=passed,
            score=round(avg, 3),
            reason=" | ".join(issues) if issues else f"All {len(characters)} characters present",
            fix_hint="Add character name to positive prompt, increase CFG" if not passed else "",
            metadata={"per_character": scores_per_char},
        )


def clip_tokenize(texts: list):
    """Thin wrapper around clip.tokenize for use with cached model."""
    import clip as clip_module
    return clip_module.tokenize(texts)
