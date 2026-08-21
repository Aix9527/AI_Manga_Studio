"""Shot DNA retrieval (Phase 13.1, GPT spec).

Feature matching: category / scene / emotion / camera.movement / lighting.
Hit rate ≥ 90% acceptance gate is tracked per retrieval batch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.shot_dna.library import ShotDNA, ShotDNALibrary


@dataclass
class RetrievalHit:
    dna: ShotDNA
    score: float
    matched: list[str]


class ShotDNARetriever:
    def __init__(self, library: ShotDNALibrary | None = None):
        self.library = library or ShotDNALibrary()
        self._attempts = 0
        self._hits = 0

    def retrieve(
        self,
        *,
        category: str = "",
        scene: str = "",
        emotion: str = "",
        camera_movement: str = "",
        lighting: str = "",
        top_k: int = 3,
    ) -> list[RetrievalHit]:
        query = {
            "category": category.lower().strip(),
            "scene": scene.lower().strip(),
            "emotion": emotion.lower().strip(),
            "camera_movement": camera_movement.lower().strip(),
            "lighting": lighting.lower().strip(),
        }
        scored: list[RetrievalHit] = []
        for dna in self.library.all():
            matched: list[str] = []
            score = 0.0
            if query["category"] and query["category"] == dna.category:
                score += 2.0
                matched.append("category")
            if query["scene"] and query["scene"] in (dna.scene.lower(), *[t.lower() for t in dna.tags]):
                score += 1.0
                matched.append("scene")
            if query["emotion"] and query["emotion"] in dna.emotion.lower():
                score += 1.0
                matched.append("emotion")
            if query["camera_movement"] and query["camera_movement"] in str(dna.camera.get("movement", "")).lower():
                score += 1.0
                matched.append("camera_movement")
            if query["lighting"] and query["lighting"] in dna.lighting.lower():
                score += 1.0
                matched.append("lighting")
            if score > 0:
                scored.append(RetrievalHit(dna=dna, score=score, matched=matched))
        scored.sort(key=lambda hit: (hit.score, hit.dna.success_rate), reverse=True)
        return scored[:top_k]

    def retrieve_with_stats(self, **kwargs) -> dict:
        """Return ranked hits + whether the batch counts as a hit."""
        hits = self.retrieve(**kwargs)
        top = hits[0] if hits else None
        is_hit = top is not None and top.score >= 2.0  # category + at least one feature
        self._attempts += 1
        if is_hit:
            self._hits += 1
        return {
            "query": {k: v for k, v in kwargs.items()},
            "hits": [
                {
                    "id": h.dna.id,
                    "category": h.dna.category,
                    "scene": h.dna.scene,
                    "camera": h.dna.camera,
                    "lens": h.dna.lens,
                    "lighting": h.dna.lighting,
                    "emotion": h.dna.emotion,
                    "success_rate": h.dna.success_rate,
                    "usage_count": h.dna.usage_count,
                    "prompt_template": h.dna.prompt_template,
                    "score": h.score,
                    "matched": h.matched,
                }
                for h in hits
            ],
            "is_hit": is_hit,
        }

    def hit_rate(self) -> dict:
        rate = self._hits / self._attempts if self._attempts else 0.0
        return {"attempts": self._attempts, "hits": self._hits, "hit_rate": round(rate, 3)}
