"""
Image Analyzer — Sprint 7.1 Vision Critic.
CLIP-based image understanding, aesthetic scoring, compositional analysis.

Uses torch + transformers for CLIP, falls back gracefully.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json
import hashlib


@dataclass
class ImageProfile:
    """Extracted profile from a generated image."""
    image_path: str = ""
    image_hash: str = ""

    # CLIP analysis
    aesthetic_score: float = 0.0       # 0.0–1.0
    content_tags: list[str] = field(default_factory=list)

    # Composition
    composition_type: str = "unknown"   # close-up, medium, wide, dutch-angle, etc.
    rule_of_thirds: float = 0.0         # how well it follows the rule
    subject_centered: bool = True
    depth_perceived: str = "flat"       # flat, medium, deep

    # Technical
    sharpness: float = 0.0              # 0.0–1.0
    exposure: str = "normal"            # underexposed, normal, overexposed
    color_harmony: float = 0.0          # 0.0–1.0

    # Character detection
    character_count: int = 0
    faces_detected: int = 0

    # Raw
    raw_response: str = ""


class ImageAnalyzer:
    """
    Core image analyzer.

    Uses CLIP (ViT-B/32) for semantic understanding when available.
    Falls back to heuristics + PIL-based analysis when CLIP is unavailable.
    """

    def __init__(self):
        self._clip_model = None
        self._clip_processor = None
        self._clip_available = False
        self._try_load_clip()

    def _try_load_clip(self):
        """Try to load CLIP model. Gracefully degrade if unavailable."""
        try:
            import torch
            from transformers import CLIPProcessor, CLIPModel

            self._clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
            self._clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
            self._clip_available = True
        except Exception:
            self._clip_available = False

    def analyze(self, image_path: str) -> ImageProfile:
        """Full image analysis pipeline."""
        profile = ImageProfile(image_path=image_path)

        if not Path(image_path).exists():
            profile.raw_response = f"Image not found: {image_path}"
            return profile

        # Compute hash
        profile.image_hash = self._hash_image(image_path)

        # Basic PIL analysis (always available)
        self._analyze_pil(image_path, profile)

        # CLIP semantic analysis
        if self._clip_available:
            self._analyze_clip(image_path, profile)

        # Aggregated aesthetic score
        profile.aesthetic_score = self._compute_aesthetic(profile)

        return profile

    def batch_analyze(self, image_paths: list[str]) -> list[ImageProfile]:
        """Analyze multiple images."""
        return [self.analyze(p) for p in image_paths]

    # ── PIL Analysis ────────────────────────────────────────────

    def _analyze_pil(self, path: str, profile: ImageProfile):
        """PIL-based technical analysis."""
        try:
            from PIL import Image, ImageStat
            import numpy as np

            img = Image.open(path).convert("RGB")
            w, h = img.size
            stat = ImageStat.Stat(img)

            # Sharpness via Laplacian variance
            arr = np.array(img.convert("L"), dtype=np.float64)
            luma_var = np.var(arr)
            profile.sharpness = min(luma_var / 5000.0, 1.0)

            # Exposure assessment from mean brightness
            mean_brightness = stat.mean[0]  # R channel mean
            if mean_brightness < 80:
                profile.exposure = "underexposed"
            elif mean_brightness > 200:
                profile.exposure = "overexposed"
            else:
                profile.exposure = "normal"

            # Color harmony via channel variance ratio
            r_var, g_var, b_var = stat.var[0], stat.var[1], stat.var[2]
            total_var = r_var + g_var + b_var
            if total_var > 0:
                ratios = sorted([r_var, g_var, b_var])[::-1]
                profile.color_harmony = ratios[1] / ratios[0] if ratios[0] > 0 else 0

            # Rule of thirds
            center_r = arr[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4]
            edge_mask = np.ones(arr.shape, dtype=bool)
            edge_mask[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4] = False
            edges = arr[edge_mask]

            center_mean = np.mean(center_r) if center_r.size > 0 else 0
            edge_mean = np.mean(edges) if edges.size > 0 else 0
            profile.rule_of_thirds = 1.0 - min(abs(center_mean - edge_mean) / 128.0, 1.0)
            profile.subject_centered = abs(center_mean - edge_mean) > 30

        except Exception as e:
            profile.raw_response += f"[PIL error: {e}]"

    # ── CLIP Analysis ───────────────────────────────────────────

    def _analyze_clip(self, path: str, profile: ImageProfile):
        """CLIP-based semantic analysis."""
        try:
            from PIL import Image

            image = Image.open(path).convert("RGB")
            inputs = self._clip_processor(images=image, return_tensors="pt")

            # Aesthetic score
            aesthetic_prompts = [
                "a beautiful masterpiece, high quality artwork",
                "a poorly drawn, low quality image",
            ]
            aesthetic_inputs = self._clip_processor(
                text=aesthetic_prompts, return_tensors="pt", padding=True
            )

            import torch
            with torch.no_grad():
                image_features = self._clip_model.get_image_features(**inputs)
                text_features = self._clip_model.get_text_features(**aesthetic_inputs)

                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)

                similarity = (image_features @ text_features.T).squeeze(0)
                profile.aesthetic_score = float(
                    torch.softmax(similarity, dim=0)[0].item()
                )

            # Content tags
            tag_candidates = [
                "manga style", "anime style", "realistic", "painterly",
                "character portrait", "action scene", "landscape", "dialogue scene",
                "close up", "wide shot", "dutch angle", "overhead shot",
                "dramatic lighting", "soft lighting", "dark atmosphere",
                "single character", "multiple characters", "no characters",
                "dynamic pose", "static pose", "fighting", "talking",
            ]
            tag_inputs = self._clip_processor(text=tag_candidates, return_tensors="pt", padding=True)

            with torch.no_grad():
                tag_features = self._clip_model.get_text_features(**tag_inputs)
                tag_features = tag_features / tag_features.norm(dim=-1, keepdim=True)
                sims = (image_features @ tag_features.T).squeeze(0)
                threshold = 0.22
                for i, tag in enumerate(tag_candidates):
                    if float(sims[i]) > threshold:
                        profile.content_tags.append(tag)

            # Composition type detection
            comp_candidates = ["close-up shot", "medium shot", "wide shot", "dutch angle shot"]
            comp_inputs = self._clip_processor(text=comp_candidates, return_tensors="pt", padding=True)
            with torch.no_grad():
                comp_features = self._clip_model.get_text_features(**comp_inputs)
                comp_features = comp_features / comp_features.norm(dim=-1, keepdim=True)
                comp_sims = (image_features @ comp_features.T).squeeze(0)
                best_idx = int(torch.argmax(comp_sims))
                profile.composition_type = ["close-up", "medium", "wide", "dutch-angle"][best_idx]

        except Exception as e:
            profile.raw_response += f"[CLIP error: {e}]"

    # ── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _compute_aesthetic(profile: ImageProfile) -> float:
        """Aggregate aesthetic score from sub-scores."""
        weights = {
            "sharpness": 0.15,
            "color_harmony": 0.20,
            "rule_of_thirds": 0.15,
            "exposure_ok": 0.10,
        }

        score = 0.0
        score += profile.sharpness * weights["sharpness"]
        score += profile.color_harmony * weights["color_harmony"]
        score += profile.rule_of_thirds * weights["rule_of_thirds"]
        score += (1.0 if profile.exposure == "normal" else 0.4) * weights["exposure_ok"]

        # CLIP aesthetic (if available) adds 40%
        if profile.aesthetic_score > 0:
            score = score * 0.6 + profile.aesthetic_score * 0.4

        return round(min(score, 1.0), 4)

    @staticmethod
    def _hash_image(path: str) -> str:
        """SHA-256 hash of image file."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
