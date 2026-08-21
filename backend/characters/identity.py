from __future__ import annotations

import hashlib
from typing import Sequence

from backend.characters.embedding import CharacterEmbedder


class IdentityEngine:
    """Multi-character identity lock (DiffSensei-inspired).

    Verifies that *every* expected character is present in a generated image
    by comparing a single image embedding against per-character reference
    embeddings. Also exposes a stable identity fingerprint.
    """

    def __init__(self, embedder: CharacterEmbedder | None = None, threshold: float = 0.75):
        self.embedder = embedder or CharacterEmbedder()
        self.threshold = threshold

    @staticmethod
    def cosine(a: Sequence[float], b: Sequence[float]) -> float:
        import math
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def multi_character_lock(
        self,
        reference_embeddings: dict[str, Sequence[float]],
        image_path: str,
    ) -> dict:
        """Check all expected characters at once.

        Args:
            reference_embeddings: {character_id: embedding_vector}
            image_path: generated image to verify.

        Returns:
            {
              "per_character": [{character_id, score, verdict}],
              "overall_verdict": "pass" | "fail",
              "missing": [character_id, ...],
              "threshold": float,
            }
        """
        gen = self.embedder.embed_image(image_path)
        per = []
        missing = []
        for cid, ref in reference_embeddings.items():
            score = self.cosine(ref, gen)
            ok = score >= self.threshold
            per.append({"character_id": cid, "score": round(score, 4), "verdict": "pass" if ok else "fail"})
            if not ok:
                missing.append(cid)
        return {
            "per_character": per,
            "overall_verdict": "pass" if not missing else "fail",
            "missing": missing,
            "threshold": self.threshold,
        }

    def fingerprint(self, character_id: str, image_path: str) -> str:
        """Stable identity fingerprint = embedding hash + image content hash."""
        emb = self.embedder.embed_image(image_path)
        emb_bytes = ",".join(f"{v:.6f}" for v in emb).encode("utf-8")
        h = hashlib.sha256(emb_bytes).hexdigest()[:16]
        return f"{character_id}:{h}"
