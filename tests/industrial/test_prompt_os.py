"""Phase 13.6: Prompt OS tests (DNA / ShotDesign 8-layer / Compiler / Evolution)."""

from __future__ import annotations

import pytest

from backend.prompt_os.evolution import PromptEvolution
from backend.prompt_os.service import PromptOS
from backend.prompt_os.model import SHOTDESIGN_LAYERS, DNA_KINDS


@pytest.fixture()
def os_(tmp_path):
    return PromptOS(str(tmp_path / "pos"))


@pytest.fixture()
def os_evolving(tmp_path):
    ev = PromptEvolution(str(tmp_path / "pos_ev"), min_samples=2, min_score=0.3)
    return PromptOS(str(tmp_path / "pos2"), evolution=ev)


# ---------------------------------------------------------------- DNA
def test_dna_seed_covers_all_kinds(os_):
    stats = os_.dna_stats()
    assert stats["entries"] > 40
    for kind in DNA_KINDS:
        assert kind in stats["by_kind"]
        assert stats["by_kind"][kind] >= 3


def test_dna_continuity_and_negative(os_):
    continuity = os_.dna_by_kind("continuity")
    negative = os_.dna_by_kind("negative")
    assert any("character_state_inherit" in str(c["values"]) for c in continuity)
    failures = []
    for n in negative:
        failures.extend(n["values"].get("failures", []))
    assert "表情僵硬" in failures
    assert "换脸" in failures


def test_dna_add_and_get(os_):
    row = os_.dna_add({"kind": "style", "name": "测试风格", "values": {"visual": "高饱和"}})
    assert row["id"]
    got = os_.dna_by_kind("style")
    assert any(e["id"] == row["id"] for e in got)


# ---------------------------------------------------------------- Compiler
def test_compile_single_shot_eight_layers(os_):
    design = os_.compile_shot("少年进入地下遗迹", duration_seconds=10.0)
    assert design["duration_seconds"] == 10.0
    assert set(design["layers"].keys()) == set(SHOTDESIGN_LAYERS)
    assert "地下遗迹" in design["layers"]["story"]
    assert design["layers"]["photography"]["lens"]
    assert design["layers"]["camera_movement"]
    assert design["continuity_contract"]["constraints"]
    assert design["negative_words"]


def test_compile_sequence_connects_transitions(os_):
    shots = os_.compile_sequence(["少年进入地下遗迹", "少年回眸望向黑暗", "少年拔剑"])
    assert len(shots) == 3
    assert shots[0]["transition_out"] == shots[1]["transition_in"]
    assert shots[1]["transition_out"] == shots[2]["transition_in"]
    # continuity 继承：第二镜约束包含第一镜场景
    assert shots[1]["continuity_contract"]["characters"]
    assert shots[2]["continuity_contract"]["space"]


def test_compile_empty_logline_rejected(os_):
    with pytest.raises(ValueError, match="logline"):
        os_.compile_shot("   ")


# ---------------------------------------------------------------- versioning
def test_shot_design_approve_lock_and_derive(os_):
    design = os_.compile_shot("少年进入地下遗迹")
    did = design["id"]
    with pytest.raises(ValueError, match="approved"):
        os_.set_status(did, "locked")
    os_.set_status(did, "approved", approved_by="导演")
    os_.set_status(did, "locked")
    v2 = os_.new_version(did, overrides={"layers": {"director_intent": "强化压迫感"}}, notes="GPT 建议增强")
    assert v2["version"] == "v2"
    assert v2["parent_version"] == "v1"
    assert v2["status"] == "draft"
    assert v2["layers"]["director_intent"] == "强化压迫感"
    # 原版本不被修改
    original = os_.get_shot_design(did)
    assert original.layers["director_intent"] != "强化压迫感"


# ---------------------------------------------------------------- engines
def test_ten_engines_registered(os_):
    engines = os_.engines()
    keys = [e["key"] for e in engines]
    assert set(keys) == {"character", "scene", "camera", "story", "video",
                         "voice", "qc", "compiler", "optimizer", "evolution"}
    assert all(e["status"] == "active" for e in engines)


def test_run_qc_engine_returns_negative_words(os_):
    out = os_.run_engine("qc", {"negative_ids": None})
    assert out["count"] >= 20
    assert "表情僵硬" in out["negative_prompt"]


def test_run_compiler_engine_saves_design(os_):
    out = os_.run_engine("compiler", {"logline": "少年进入地下遗迹", "lens": "24mm"})
    assert out["shot_design"]["layers"]["photography"]["lens"] == "24mm"
    assert os_.get_shot_design(out["shot_design"]["id"]) is not None


def test_run_story_engine(os_):
    out = os_.run_engine("story", {"logline": "少女绝望回头"})
    assert out["director_intent"]


def test_unknown_engine_rejected(os_):
    with pytest.raises(KeyError, match="engine not found"):
        os_.run_engine("nope", {})


# ---------------------------------------------------------------- evolution
def test_evolution_metric_score_and_candidate(os_evolving):
    design = os_evolving.compile_shot("少年进入地下遗迹", duration_seconds=10.0)
    did = design["id"]
    for _ in range(3):
        os_evolving.record_metric(shot_design_id=did, completion_rate=0.7, like_rate=0.3,
                                  comment_rate=0.2, favorite_rate=0.25, views=5000)
    board = os_evolving.leaderboard()
    assert board[0]["shot_design_id"] == did
    assert board[0]["samples"] == 3
    candidates = os_evolving.propose_candidates()
    assert len(candidates) == 1
    assert candidates[0]["status"] == "candidate"
    assert candidates[0]["suggested_layers"]


def test_evolution_approval_flow_and_no_auto_apply(os_evolving):
    design = os_evolving.compile_shot("少年进入地下遗迹")
    did = design["id"]
    for _ in range(3):
        os_evolving.record_metric(shot_design_id=did, completion_rate=0.8, like_rate=0.4,
                                  comment_rate=0.3, favorite_rate=0.35, views=9000)
    candidate = os_evolving.propose_candidates()[0]
    rid = candidate["id"]
    # 未审批直接应用被拒绝（auto_apply=false）
    with pytest.raises(ValueError, match="approved"):
        os_evolving.apply_candidate(rid)
    os_evolving.review_candidate(rid, "approved", reviewer="制片人")
    applied = os_evolving.apply_candidate(rid)
    assert applied["status"] == "applied"
    assert applied["applied_version"]
    # 重复应用被拒绝
    with pytest.raises(ValueError, match="applied"):
        os_evolving.apply_candidate(rid)


def test_evolution_reject_path(os_evolving):
    design = os_evolving.compile_shot("少女走进宫殿")
    did = design["id"]
    for _ in range(3):
        os_evolving.record_metric(shot_design_id=did, completion_rate=0.6, like_rate=0.2,
                                  comment_rate=0.1, favorite_rate=0.15, views=3000)
    candidate = os_evolving.propose_candidates()[0]
    os_evolving.review_candidate(candidate["id"], "rejected", reviewer="导演")
    records = os_evolving.evolution_records(status="rejected")
    assert records[0]["id"] == candidate["id"]


def test_evolution_stats_expose_frozen_flags(os_evolving):
    stats = os_evolving.evolution_stats()
    assert stats["auto_learning"] is False
    assert stats["auto_apply"] is False
    assert stats["weights"]["completion"] == 0.5


def test_review_invalid_decision_rejected(os_evolving):
    design = os_evolving.compile_shot("少年进入地下遗迹")
    did = design["id"]
    for _ in range(3):
        os_evolving.record_metric(shot_design_id=did, completion_rate=0.8, like_rate=0.4,
                                  comment_rate=0.3, favorite_rate=0.35, views=9000)
    candidate = os_evolving.propose_candidates()[0]
    with pytest.raises(ValueError, match="approved 或 rejected"):
        os_evolving.review_candidate(candidate["id"], "maybe")