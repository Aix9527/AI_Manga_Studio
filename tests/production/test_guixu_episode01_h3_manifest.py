from __future__ import annotations

import json
from pathlib import Path


MANIFEST = Path("data/production/guixu_episode01_h3_v1.json")


def _load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_has_complete_ordered_timeline() -> None:
    data = _load_manifest()
    shots = data["shots"]

    assert len(shots) == 27
    assert shots[0]["start_s"] == 0
    assert shots[-1]["end_s"] == 130
    assert all(
        current["end_s"] == following["start_s"]
        for current, following in zip(shots, shots[1:])
    )
    assert sum(shot["target_s"] for shot in shots) == 130


def test_manifest_has_25_video_segments_and_two_cards() -> None:
    shots = _load_manifest()["shots"]

    assert sum(
        shot["workflow"] in {"standard", "reference"}
        for shot in shots
    ) == 25
    assert [shot["id"] for shot in shots if shot["workflow"] == "card"] == [
        "S02",
        "S21",
    ]


def test_reference_shots_only_use_known_anchors() -> None:
    data = _load_manifest()
    known = set(data["anchors"])

    for shot in data["shots"]:
        assert set(shot["refs"]).issubset(known)
        if shot["workflow"] == "reference":
            assert shot["refs"]


def test_first_episode_gold_rule_is_explicit() -> None:
    for shot in _load_manifest()["shots"]:
        if shot["id"] != "S21":
            assert "无金色元素" in shot["prompt"]

