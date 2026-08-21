from __future__ import annotations

from pathlib import Path

from backend.characters.identity import IdentityEngine
from backend.video.identity_gate import IdentityVerifier


class FakeEmbedder:
    """Deterministic embedder: image filename selects the vector."""

    def __init__(self):
        self.calls = 0

    def embed_image(self, image_path: str) -> list[float]:
        self.calls += 1
        name = Path(image_path).stem
        # frame_a_*.png -> SuWan vector, frame_b_*.png -> ChenYe vector
        if "b_" in name:
            return [0.0, 1.0]
        return [1.0, 0.0]


def _fake_extractor(video_path: Path, out_dir: Path, num_frames: int) -> list[Path]:
    """Emit synthetic frame paths: first 4 frames of character A, last of B."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(num_frames):
        name = "frame_a_%02d.png" % i if i < num_frames - 1 else "frame_b_%02d.png" % i
        f = out_dir / name
        f.write_bytes(b"frame")
        paths.append(f)
    return paths


def _engine():
    return IdentityEngine(embedder=FakeEmbedder(), threshold=0.75)


def test_character_present_passes():
    verifier = IdentityVerifier(engine=_engine(), frame_extractor=_fake_extractor)
    refs = {"suwan": [1.0, 0.0]}
    report = verifier.verify_video("clip.mp4", refs)
    assert report.overall_verdict == "pass"
    assert report.per_character["suwan"]["verdict"] == "pass"
    assert report.per_character["suwan"]["presence_ratio"] >= 0.6
    assert report.frames_checked == 5


def test_swapped_character_fails():
    """Acceptance: deliberately swap the character -> detection must fail."""
    verifier = IdentityVerifier(engine=_engine(), frame_extractor=_fake_extractor)
    refs = {"suwan": [1.0, 0.0]}
    report = verifier.verify_video("clip.mp4", refs)
    # Frames mostly show suwan -> pass. Now swap: claim the clip is ChenYe.
    swapped = verifier.verify_video("clip.mp4", {"chenye": [0.0, 1.0]})
    # chenye appears in only 1/5 frames -> fail
    assert swapped.overall_verdict == "fail"
    assert swapped.per_character["chenye"]["verdict"] == "fail"
    assert swapped.per_character["chenye"]["frames_present"] == 1


def test_multi_character_requires_everyone():
    verifier = IdentityVerifier(engine=_engine(), frame_extractor=_fake_extractor)
    refs = {"suwan": [1.0, 0.0], "chenye": [0.0, 1.0]}
    report = verifier.verify_video("clip.mp4", refs)
    # suwan present in 4/5, chenye only 1/5 -> overall fail
    assert report.overall_verdict == "fail"
    assert report.per_character["suwan"]["verdict"] == "pass"
    assert report.per_character["chenye"]["verdict"] == "fail"
