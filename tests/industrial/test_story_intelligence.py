"""Phase 13.2: Story Intelligence tests (GPT spec)."""

from __future__ import annotations

import pytest

from backend.agents.episode_planner import EpisodePlannerAgent
from backend.agents.executive_producer import ExecutiveProducerAgent
from backend.agents.retention import RetentionIntelligenceEngine
from backend.agents.world_analyzer import WorldAnalyzerAgent
from backend.story.episode.repository import EpisodeRepository
from backend.story.episode.service import EpisodeService
from backend.world.service import WorldService

NOVEL = (
    "主角「陈夜」觉醒量子能力，封印着毁灭世界的力量。"
    "未来都市中 AI 文明崛起，他发现自己身世的秘密指向古遗迹。"
    "反派「墨渊」步步紧逼，时间回溯的禁忌逐渐浮现。"
)


@pytest.fixture()
def episode_service(tmp_path):
    return EpisodeService(EpisodeRepository(str(tmp_path / "episodes.db")))


@pytest.fixture()
def world_service(tmp_path):
    return WorldService(str(tmp_path / "world"))


def test_executive_producer_generates_100_episode_plan(episode_service):
    agent = ExecutiveProducerAgent(episode_service)
    plan = agent.plan(NOVEL, project_id="PROJ-100", target_episodes=100, write_episodes=False)
    assert plan.target_episodes == 100
    assert len(plan.episodes) == 100
    assert all(ep["hook"] for ep in plan.episodes)
    assert all(ep["conflict"] for ep in plan.episodes)
    assert all(ep["climax"] for ep in plan.episodes)
    assert all(ep["ending"] for ep in plan.episodes)
    assert all(ep["retention_strategy"] for ep in plan.episodes)
    # meta: hero extracted
    assert plan.meta["hero"] == "陈夜"


def test_executive_producer_persists_draft_episodes(episode_service):
    agent = ExecutiveProducerAgent(episode_service)
    plan = agent.plan(NOVEL, project_id="PROJ-D", target_episodes=3, write_episodes=True)
    episodes = episode_service.list_by_project("PROJ-D")
    assert len(episodes) == 3
    # human approval gate: all stay DRAFT, never auto-advance
    assert all(ep.status == "draft" for ep in episodes)
    assert all(ep.hook for ep in episodes)
    # audit trail exists per episode
    assert any(episode_service.audit(ep.id) for ep in episodes)


def test_pipeline_estimate(episode_service):
    agent = ExecutiveProducerAgent(episode_service)
    plan = agent.plan(NOVEL, project_id="PROJ-E", target_episodes=100, target_duration=90.0, write_episodes=False)
    estimate = agent.plan_pipeline_estimate(plan)
    assert estimate["total_shots"] == 1800
    assert estimate["episodes"] == 100
    assert estimate["estimated_gpu_hours"] > 0


def test_episode_planner_fills_hooks_100_percent(episode_service):
    producer = ExecutiveProducerAgent(episode_service)
    producer.plan("一句话开局。", project_id="PROJ-P", target_episodes=5, write_episodes=True)
    # wipe plan fields to simulate sparse records
    for ep in episode_service.list_by_project("PROJ-P"):
        episode_service.update_plan(ep.id, hook="", conflict="", climax="", ending="", retention_strategy="")
    planner = EpisodePlannerAgent(episode_service)
    result = planner.plan_project("PROJ-P")
    assert result["total"] == 5
    assert result["planned"] == 5
    assert result["hook_coverage"] == 1.0
    for ep in episode_service.list_by_project("PROJ-P"):
        assert ep.hook and ep.conflict and ep.climax and ep.ending and ep.retention_strategy


def test_episode_planner_single_missing_episode_raises(episode_service):
    planner = EpisodePlannerAgent(episode_service)
    with pytest.raises(KeyError):
        planner.plan_episode("NOPE")


def test_world_analyzer_extracts_world_bible(world_service):
    agent = WorldAnalyzerAgent(world_service)
    world = agent.analyze("PROJ-W", NOVEL, name="归墟")
    assert world["era"] == "未来科幻"
    assert world["technology"] == "高端科技" or world["technology"]
    assert world["power_system"] == "特殊力量体系"
    assert world["visual_style"] in ("赛博朋克", "东方奇幻", "写实")
    # world bible is queryable
    assert world_service.get_world(world["id"]) is not None
    # environment memory recorded
    assert world_service.environment_summary("PROJ-W")["entries"] >= 1


def test_retention_scoring_rules():
    engine = RetentionIntelligenceEngine()
    result = engine.score_episode(
        hook="陈夜撞见墨渊，生死一线",
        conflict="身份被揭开，追兵已至",
        climax="觉醒隐藏力量，逆转战局",
        ending="黑暗尽头，墨渊的声音响起",
        retention_strategy="cliffhanger_question",
    )
    assert 0.0 <= result["hook_score"] <= 1.0
    assert 0.0 <= result["emotion_curve"] <= 1.0
    assert result["cliffhanger_score"] >= 0.5  # cliffhanger scoring PASS
    assert result["share_probability"] >= 0.0
    assert result["formula_check"]["0_3s_hook"] is True
    assert result["formula_check"]["end_cliffhanger"] is True


def test_retention_empty_episode_scores_zero():
    engine = RetentionIntelligenceEngine()
    result = engine.score_episode()
    assert result["hook_score"] == 0.0
    assert result["cliffhanger_score"] == 0.0


def test_retention_plan_aggregate():
    engine = RetentionIntelligenceEngine()
    plan = [
        {"hook": "h1", "conflict": "c1", "climax": "x1", "ending": "e1？", "retention_strategy": "cliffhanger_question"},
        {"hook": "h2", "conflict": "c2", "climax": "x2", "ending": "e2", "retention_strategy": "power_display"},
    ]
    result = engine.score_plan(plan)
    assert result["episodes"] == 2
    assert 0.0 <= result["average"]["hook_score"] <= 1.0
    assert result["hook_coverage"] == 1.0
