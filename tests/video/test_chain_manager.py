from __future__ import annotations

from backend.video.chain_manager import ChainManager, KeyframeMemory


def _shot(sid: str, location: str, tod: str = "night") -> dict:
    return {"id": sid, "location": location, "time_of_day": tod}


def test_first_shot_is_keyframe():
    cm = ChainManager()
    links = cm.plan_chain([_shot("gx_001", "实验室")])
    assert links[0].mode == "keyframe"


def test_same_space_chains_tailframe():
    cm = ChainManager(memory=KeyframeMemory())
    cm.advance("gx_001", "last_frame_001.png", {"location": "实验室", "time_of_day": "night"})
    links = cm.plan_chain([
        _shot("gx_001", "实验室"),
        _shot("gx_002", "实验室"),
        _shot("gx_003", "地下"),
    ])
    assert links[0].mode == "keyframe"     # first shot
    assert links[1].mode == "last_frame"   # same space -> tail chain
    assert links[2].mode == "reset"        # scene break
    assert links[1].start_image == "last_frame_001.png"


def test_chain_report_counts_modes():
    cm = ChainManager(memory=KeyframeMemory())
    cm.advance("gx_001", "lf1.png", {"location": "实验室", "time_of_day": "night"})
    links = cm.plan_chain([_shot("gx_001", "实验室"), _shot("gx_002", "实验室")])
    rep = cm.chain_report(links)
    assert rep["total"] == 2
    assert rep["by_mode"]["keyframe"] == 1
    assert rep["by_mode"]["last_frame"] == 1
