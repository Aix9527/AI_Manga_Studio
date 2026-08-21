from __future__ import annotations

from backend.characters.embedding import CharacterEmbedder
from backend.characters.identity import IdentityEngine


class _FakeEmbedder(CharacterEmbedder):
    """Deterministic fake: vector derived from the path so tests don't need CLIP."""

    def embed_image(self, image_path: str):
        import hashlib
        h = hashlib.sha256(str(image_path).encode()).digest()
        return [b / 255.0 for b in h[:8]]


def test_multi_character_lock_all_pass(tmp_path):
    eng = IdentityEngine(embedder=_FakeEmbedder(), threshold=0.5)
    img = tmp_path / "gen.png"
    img.write_bytes(b"x")
    refs = {"苏晚": eng.embedder.embed_image("ref_suwan.png"),
            "陈夜": eng.embedder.embed_image("ref_chenye.png")}
    res = eng.multi_character_lock(refs, str(img))
    assert res["overall_verdict"] == "pass"
    assert len(res["per_character"]) == 2


def test_fingerprint_stable():
    eng = IdentityEngine(embedder=_FakeEmbedder())
    f1 = eng.fingerprint("苏晚", "a.png")
    f2 = eng.fingerprint("苏晚", "a.png")
    f3 = eng.fingerprint("苏晚", "b.png")
    assert f1 == f2
    assert f1 != f3
    assert f1.startswith("苏晚:")


def test_cosine_identical_is_one():
    v = [1.0, 0.0, 0.5]
    import pytest
    assert IdentityEngine.cosine(v, v) == pytest.approx(1.0)
    assert IdentityEngine.cosine(v, [0.0, 1.0, 0.0]) == 0.0
