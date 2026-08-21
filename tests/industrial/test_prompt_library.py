"""Phase 15.3-B: Prompt Library tests（CINEDANCE 骨架 / 编译 / MiniMax 参数）. """

from __future__ import annotations

import pytest

from backend.prompt_library.service import PromptLibrary


@pytest.fixture()
def lib():
    return PromptLibrary()


def test_template_15_sections(lib):
    tpl = lib.template()
    assert len(tpl["sections"]) == 15
    keys = [s["key"] for s in tpl["sections"]]
    assert "scene_context" in keys and "positive_constraints" in keys
    assert "style_prefix" in tpl and "8K IMAX" in tpl["style_prefix"]


def test_wording_rules_and_minimax(lib):
    rules = lib.wording_rules()
    assert any("现在时" in r or "肯定式" in r for r in rules)
    params = lib.minimax_params()
    assert params["fps"] == 24
    assert params["duration_range_s"] == [4, 15]


def test_compile_shot_full(lib):
    prompt = lib.compile_shot(
        characters=["ROCO", "JAX"],
        location="地下训练厅：中央圆垫，门在画面左，约八米外，相机在门侧永不越线",
        action="ROCO 独自训练数小时后，JAX 端着餐盘走进来",
        duration_s=15,
        beats=["0.0–2.0s 房间静止；2.0–6.0s 门开，JAX 进入；6.0–12.0s ROCO 转头；12.0–15.0s 对视，无人移动"],
        optics="≈40° 广角，机位胸口高度",
        camera="平静呼吸式手持，无推拉变焦",
        lighting="单头顶硬光，逆光勾勒",
        audio="仅环境音，无音乐",
        acting="ROCO 疲惫但不停：想要再干净打一次；JAX 端着托盘，反应慢半拍",
    )
    assert "EXACT 2 CHARACTERS" in prompt
    assert "SCENE CONTEXT" in prompt and "POSITIVE CONSTRAINTS" in prompt
    assert "@ROCO for character reference" in prompt
    assert "15 秒" in prompt
    assert "8K IMAX" in prompt
    assert "不写年龄" in prompt
