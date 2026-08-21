"""AI_Manga_Studio v1.0 Phase 3-9 tests. """

from __future__ import annotations

import pytest

from backend.consistency.engine import CinemaJudge, IdentityLock, MotionMemory, RepairEngine, SceneMemory
from backend.studio.factory import ProductionFactory
from backend.evolution.engine import DirectorEvolution, FailurePattern
from backend.studio_v2.platform import (
    CreativeBrain, FilmCertifier, IPManager, ProjectManager, RenderScheduler,
    StudioCouncil, TemplateMarket, WorkerRegistry,
)


# ------------------------------------------------------------- Phase 3
def test_identity_lock_detects_drift(tmp_path):
    lock = IdentityLock(str(tmp_path / "c"))
    lock.register(character="陈夜", fixed={"hair": "black", "costume": "black robe"})
    ok = lock.check(character="陈夜", observed={"hair": "black", "costume": "black robe"}, face_similarity=0.92)
    assert ok["passed"] is True
    drift = lock.check(character="陈夜", observed={"hair": "black", "costume": "white armor"}, face_similarity=0.6)
    assert drift["passed"] is False
    assert "face_drift" in drift["issues"]
    assert "COSTUME_CHANGED:costume" in drift["issues"]


def test_scene_and_repair(tmp_path):
    scene = SceneMemory(str(tmp_path / "c"))
    scene.register_scene(scene="地下城", architecture=["bronze wall"], lighting="cyan", color="bronze black")
    drift = scene.check(scene="地下城", observed={"architecture": ["modern office"], "lighting": "cyan", "color": "bronze black"})
    assert drift["passed"] is False
    repair = RepairEngine(str(tmp_path / "r"))
    plan = repair.repair(shot_id="S1", issues=["face_drift"])
    assert plan["rerun"] is True
    assert plan["repair_plan"][0]["action"] == "IPAdapter strength +15%, face reference"


def test_cinema_judge():
    judge = CinemaJudge()
    result = judge.score(visual_quality=90, character=85, motion=80,
                         cinematic_language=88, emotion=75, continuity=90)
    assert 80 <= result["score"] <= 95
    assert result["recommendation"] in ("approve", "review")
    assert result["level"] in ("cinema", "commercial")


# ------------------------------------------------------------- Phase 4
def test_production_factory_season_plan():
    factory = ProductionFactory()
    plan = factory.produce_season_plan(
        title="归墟", content="陈夜发现地下入口\n他走入青铜大厅",
        characters=["陈夜"], locations=["地下城"], episodes=12, shots_per_episode=60,
    )
    assert plan["total_shots"] == 12 * 60
    assert plan["season"]["episodes"][0]["id"] == "EP01"
    assert plan["assets"]["characters"]["陈夜"]


# ------------------------------------------------------------- Phase 5
def test_director_evolution(tmp_path):
    evo = DirectorEvolution(str(tmp_path / "e"))
    evo.learn(pattern_type="hero_intro", solution={"camera": "low_angle", "lens": "35mm"}, score=92)
    evo.learn(pattern_type="hero_intro", solution={"camera": "high_angle"}, score=70)
    best = evo.direct("hero_intro")
    assert best["solution"]["camera"] == "low_angle"
    assert best["best_score"] == 92


def test_failure_pattern_library(tmp_path):
    fp = FailurePattern(str(tmp_path / "e"))
    fp.record(failure_type="face_drift", cause="reference weight too low", fix="IPAdapter +0.15")
    assert fp.fix_for("face_drift") == "IPAdapter +0.15"
    assert fp.fix_for("unknown") is None


# ------------------------------------------------------------- Phase 6-7
def test_project_and_ip_manager(tmp_path):
    pm = ProjectManager(str(tmp_path / "p"))
    project = pm.create(owner_id="A", name="归墟", project_type="SHORT_DRAMA")
    assert project["status"] == "planning"
    ip = IPManager(str(tmp_path / "p"))
    ip.register(ip_id="IP001", name="陈夜", asset_type="character", version="v12")
    assert ip.assets("IP001")[0]["version"] == "v12"


def test_studio_council():
    council = StudioCouncil()
    decision = council.ceo_decide(market_signals={"trend": "玄幻", "audience": "18-35 男性"})
    assert decision["project"]["type"] == "玄幻"
    assert decision["project"]["episodes"] == 12
    finance = council.finance_estimate(episodes=12)
    assert finance["budget"] == 300.0
    test = council.audience_test(opening="冲突爆发，主角被追杀", hook="时间循环")
    assert test["predicted_retention"] > 70


# ------------------------------------------------------------- Phase 8-9
def test_creative_brain():
    brain = CreativeBrain()
    ideas = brain.generate_ideas(market=["玄幻", "复仇"])
    assert len(ideas) == 2
    check = brain.originality_check(story="冷酷少年失忆复仇", common_tropes=["失忆", "复仇"])
    assert check["originality_score"] < 100
    curve = brain.emotion_curve()
    assert curve["beats"][0]["emotion"] == "震撼"
    assert curve["beats"][-1]["emotion"] == "反转"


def test_worker_and_certification(tmp_path):
    registry = WorkerRegistry(str(tmp_path / "w"))
    registry.register(worker_id="gpu1", worker_type="video", gpu="RTX5070Ti", memory_gb=16, models=["Wan2.2"])
    found = registry.find(model="Wan2.2")
    assert found and found[0]["id"] == "gpu1"
    scheduler = RenderScheduler()
    assert scheduler.route(task_type="video", important=True) == "high_gpu"
    certifier = FilmCertifier()
    cert = certifier.certify(technical=95, character=90, motion=88, cinematic=92, audience=90)
    assert cert["certificate"] == "S"


def test_template_market():
    market = TemplateMarket()
    assert "霸总短剧模板" in market.list("短剧")["短剧"]
    assert "英雄登场" in market.list("镜头")["镜头"]
