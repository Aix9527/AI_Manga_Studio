"""Phase 15.3-C: Prompt Skill + Douyin Workflow Adapter tests. """

from __future__ import annotations

import pytest

from backend.prompt_library.adapter import DouyinWorkflowAdapter
from backend.prompt_library.skill import PromptSkill


@pytest.fixture()
def skill():
    return PromptSkill()


def _shot_design() -> dict:
    return {
        "id": "shot-001", "episode_id": "EP001", "project_id": "guixu2",
        "duration_seconds": 15,
        "layers": {
            "story": "少年推开青铜门，踏入地下遗迹",
            "director_intent": "体现渺小与未知",
            "photography": {"shot": "wide", "lens": "24mm", "angle": "low_angle"},
            "composition": {"name": "留白", "detail": "人物位于画面下方 1/3"},
            "action": {"motion": "slow_walk", "detail": "探索入场"},
            "camera_movement": "slow_push_in",
            "lighting": {"name": "顶部冷光", "effect": "未知疏离"},
            "style": {"visual": "广角史诗"},
            "characters": [{"name": "陈夜"}],
            "location": "地下遗迹入口",
        },
        "shot_dna_id": "dna-mh3",
    }


def test_skill_write_full_prompt(skill):
    prompt = skill.write(_shot_design())
    assert "EXACT 1 CHARACTERS" in prompt
    assert "SCENE CONTEXT" in prompt
    assert "少年推开青铜门，踏入地下遗迹" in prompt
    assert "24mm wide low_angle" in prompt
    assert "15 秒" in prompt
    assert "8K IMAX" in prompt
    assert "@陈夜 for character reference" in prompt


def test_adapter_pipeline_definition(skill):
    adapter = DouyinWorkflowAdapter(root="/tmp/nonexistent-xy")
    # 不执行真实生成，仅验证链路字段可用
    design = _shot_design()
    prompt = skill.write(design)
    assert adapter.skill is skill or adapter.skill is not None
    assert "duration_s" in prompt or "秒" in prompt
