"""Phase 13.1: Shot DNA Library + retrieval hit-rate tests."""

from __future__ import annotations

import pytest

from backend.shot_dna.library import CATEGORIES, ShotDNALibrary
from backend.shot_dna.retrieval import ShotDNARetriever


@pytest.fixture()
def library(tmp_path):
    return ShotDNALibrary(str(tmp_path / "library.json"))


def test_seed_library_covers_all_categories(library):
    stats = library.stats()
    assert stats["total"] >= 18
    assert set(stats["by_category"].keys()) == set(CATEGORIES)
    assert all(count >= 2 for count in stats["by_category"].values())


def test_add_custom_dna(library):
    dna = library.add_from_dict({
        "category": "action", "scene": "sky_battle", "camera": {"movement": "aerial"},
        "lens": "20mm", "lighting": "sunset", "emotion": "fear→resolve",
    })
    assert dna.id
    assert library.get(dna.id).category == "action"


def test_retrieval_hit_rate_above_gate(library):
    retriever = ShotDNARetriever(library)
    queries = [
        {"category": "reveal", "scene": "exploration", "emotion": "curiosity", "camera_movement": "push", "lighting": "low_key"},
        {"category": "action", "scene": "battle", "emotion": "fury", "camera_movement": "handheld", "lighting": "strobe"},
        {"category": "emotion", "scene": "rain", "emotion": "grief", "camera_movement": "dolly", "lighting": "cold"},
        {"category": "dialogue", "scene": "throne", "emotion": "anger", "camera_movement": "push", "lighting": "hard"},
        {"category": "climax", "scene": "battlefield", "emotion": "victory", "camera_movement": "zoom", "lighting": "storm"},
        {"category": "transition", "scene": "crossroads", "emotion": "nostalgia", "camera_movement": "orbit", "lighting": "day"},
        {"category": "action", "scene": "street", "emotion": "panic", "camera_movement": "dolly", "lighting": "neon"},
        {"category": "emotion", "scene": "cliff", "emotion": "resolve", "camera_movement": "static", "lighting": "dawn"},
        {"category": "reveal", "scene": "battle", "emotion": "awe", "camera_movement": "crane", "lighting": "backlight"},
        {"category": "dialogue", "scene": "cafe", "emotion": "betrayal", "camera_movement": "static", "lighting": "warm"},
    ]
    results = [retriever.retrieve_with_stats(**q) for q in queries]
    assert all(r["hits"] for r in results)
    stats = retriever.hit_rate()
    assert stats["attempts"] == len(queries)
    assert stats["hits"] == len(queries)
    assert stats["hit_rate"] >= 0.9  # GPT gate: Shot DNA 检索 ≥90% 命中


def test_retrieval_returns_sorted_proven_patterns(library):
    retriever = ShotDNARetriever(library)
    result = retriever.retrieve_with_stats(category="action", scene="battle", top_k=3)
    hits = result["hits"]
    assert hits
    assert hits[0]["category"] == "action"
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_register_use_updates_stats(library):
    dna = library.all()[0]
    before = library.get(dna.id)
    library.register_use(dna.id, success=True)
    after = library.get(dna.id)
    assert after.usage_count == before.usage_count + 1
