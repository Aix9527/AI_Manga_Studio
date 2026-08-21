"""H3 Identity QC：embedding 存储 + 相似度 + 评估器"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .face_encoder import face_encoder

STORE = Path("storage/h3_identity_embeddings")


class EmbeddingStore:

    def __init__(self, root=STORE):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, embedding: np.ndarray):
        np.save(self.root / f"{key}.npy", embedding)

    def load(self, key: str) -> Optional[np.ndarray]:
        p = self.root / f"{key}.npy"
        if p.exists():
            return np.load(p)
        return None

    def keys(self):
        return [p.stem for p in self.root.glob("*.npy")]


embedding_store = EmbeddingStore()


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a / (np.linalg.norm(a) + 1e-12), b / (np.linalg.norm(b) + 1e-12)))


class H3IdentityEvaluator:

    def __init__(self, encoder=face_encoder, store=embedding_store):
        self.encoder = encoder
        self.store = store

    def register_character(self, character_id: str, reference_image: str) -> dict:
        """从参考图建立角色标准 embedding"""
        img = cv2.imread(reference_image)
        if img is None:
            return {"ok": False, "error": "image not found"}
        emb, faces = self.encoder.embed_image(img)
        if emb is None:
            return {"ok": False, "error": "no face detected in reference"}
        self.store.save(f"char_{character_id}", emb)
        return {"ok": True, "character": character_id, "faces_detected": len(faces)}

    def evaluate_video(self, character_id: str, video_path: str, shots: list[str]) -> dict:
        ref = self.store.load(f"char_{character_id}")
        if ref is None:
            return {"ok": False, "error": "character not registered"}
        embs = self.encoder.embed_video_faces(video_path)
        if not embs:
            return {"ok": False, "error": "no faces detected in video"}
        scores = [similarity(ref, e) for e in embs]
        return {
            "character": character_id,
            "shots": shots,
            "identity_similarity": round(float(np.mean(scores)), 3),
            "max_similarity": round(float(np.max(scores)), 3),
            "faces_sampled": len(scores),
            "method": "arcface_embedding",
            "model": "w600k_r50 + det_10g",
        }


h3_identity_evaluator = H3IdentityEvaluator()
