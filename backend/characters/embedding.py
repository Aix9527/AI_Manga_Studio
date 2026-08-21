"""Character embedding module for visual/textual consistency."""

from __future__ import annotations

import hashlib
import json
from typing import Optional


class CharacterEmbedder:
    """
    Generates and stores character embeddings for identity consistency.

    Supports:
    - Textual embeddings (from character description profiles)
    - Visual embeddings (from reference images, CLIP-based)
    - Placeholder mode when no ML model is available
    """

    def __init__(self, model: str = "clip-vit-large"):
        self.model = model
        self._clip = None

    def _ensure_model(self):
        if self._clip is None:
            try:
                import torch
                from transformers import CLIPProcessor, CLIPModel
                self._clip = {
                    "model": CLIPModel.from_pretrained(f"openai/{self.model}"),
                    "processor": CLIPProcessor.from_pretrained(f"openai/{self.model}"),
                }
            except Exception:
                self._clip = False

    def embed_text(self, text: str) -> list[float]:
        self._ensure_model()
        if self._clip is False:
            return self._fallback_embed(text)
        import torch
        inputs = self._clip["processor"](text=text, return_tensors="pt", padding=True, truncation=True)
        with torch.no_grad():
            emb = self._clip["model"].get_text_features(**inputs)
        return emb[0].tolist()

    def embed_image(self, image_path: str) -> list[float]:
        self._ensure_model()
        if self._clip is False:
            return self._fallback_embed(image_path)
        from PIL import Image
        img = Image.open(image_path).convert("RGB")
        import torch
        inputs = self._clip["processor"](images=img, return_tensors="pt")
        with torch.no_grad():
            emb = self._clip["model"].get_image_features(**inputs)
        return emb[0].tolist()

    @staticmethod
    def _fallback_embed(content: str) -> list[float]:
        """Deterministic hash-based fallback when CLIP is unavailable."""
        h = hashlib.sha256(content.encode()).digest()
        # Convert first 32 bytes to 32 floats in range [-1, 1]
        return [(b / 127.5 - 1.0) for b in h[:32]]

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
