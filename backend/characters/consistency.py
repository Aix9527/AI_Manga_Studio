"""Character consistency checker for image generation."""

from __future__ import annotations

from typing import Optional

from backend.characters.embedding import CharacterEmbedder
from backend.characters.repository import CharacterRepository


class ConsistencyChecker:
    """
    Validates visual consistency of generated character images
    against stored reference embeddings.
    """

    def __init__(self, db_path: str = "storage/orchestrator.db", threshold: float = 0.75):
        self.repo = CharacterRepository(db_path)
        self.embedder = CharacterEmbedder()
        self.threshold = threshold

    def check_consistency(self, character_id: str, generated_image_path: str) -> dict:
        """
        Compare a newly generated image against the character's reference embedding.
        Returns similarity score and pass/fail verdict.
        """
        ref = self.repo.get_embedding(character_id, embedding_type="visual")
        if not ref:
            return {"consistent": True, "score": 1.0, "reason": "no_reference"}

        import struct
        ref_vector = None
        if isinstance(ref["vector"], bytes) and ref["vector"]:
            ref_vector = list(struct.unpack(f"{len(ref['vector'])//4}f", ref["vector"]))

        if not ref_vector:
            return {"consistent": True, "score": 1.0, "reason": "empty_reference"}

        gen_vector = self.embedder.embed_image(generated_image_path)
        similarity = self.embedder.cosine_similarity(ref_vector, gen_vector)

        return {
            "consistent": similarity >= self.threshold,
            "score": round(similarity, 4),
            "threshold": self.threshold,
            "character_id": character_id,
        }

    def register_reference(self, character_id: str, image_path: str) -> dict:
        """Register a reference embedding from an image."""
        from backend.characters.models import CharacterEmbedding
        emb_vector = self.embedder.embed_image(image_path)

        emb = CharacterEmbedding(
            character_id=character_id,
            embedding_type="visual",
            model=self.embedder.model,
            vector=emb_vector,
        )
        self.repo.save_embedding(emb)
        return {"status": "registered", "character_id": character_id, "dimensions": len(emb_vector)}

    def register_text_profile(self, character_id: str, profile_text: str) -> dict:
        """Register a textual profile embedding."""
        from backend.characters.models import CharacterEmbedding
        emb_vector = self.embedder.embed_text(profile_text)

        emb = CharacterEmbedding(
            character_id=character_id,
            embedding_type="textual",
            model=self.embedder.model,
            vector=emb_vector,
        )
        self.repo.save_embedding(emb)
        return {"status": "registered", "character_id": character_id}
