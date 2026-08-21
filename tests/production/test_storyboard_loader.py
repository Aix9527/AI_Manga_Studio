# -*- coding: utf-8 -*-
"""Storyboard loader 单元测试（分镜 HTML/JSON -> ProductionPlan / ChainRuntime shot）。"""
from __future__ import annotations

import json

import pytest

from backend.production.storyboard_loader import (
    Storyboard,
    load_storyboard,
    parse_storyboard_html,
    storyboard_to_plan,
    storyboard_to_shot_dicts,
)

HTML = """
<html><body>
<section class="seq" id="seq-0">
S00 序章 6 镜 · 约 0 分 41 秒
镜号 景别 运镜 画面内容 台词 / 音效 时长
S00-1 大远景 拉 黑场中，远古星图缓缓浮现。 旁白（低吟）："西北海之外"。 低频轰鸣 8s
S00-2 大远景 升 断裂的不周山天柱刺破云层。 风声与岩石崩裂声 8s
</section>
<section class="seq" id="seq-1">
S01 第一章 · 垃圾DNA 24 镜 · 约 3 分 30 秒
镜号 景别 运镜 画面内容 台词 / 音效 时长
S01-1 大远景 推 深夜的京城大学剪影，仅少数窗户亮灯。 字幕：京城 · 凌晨三点十七分。 （无对白） 电流底噪 8s
S01-2 中景 推 苏晚背对镜头坐在显示器前，冷白屏光勾出她的轮廓。 （无对白） 呼吸声放大 12s
S01-3 大特写 固定 苏晚的面孔：瓷白小鹅蛋脸。 （无对白） 静音处理 8s
S01-4 特写 摇 从桌角铝合金急救箱摇向屏幕。 字幕：自检结果 · 匹配度 99.7% 电子音效 6s
S01-5 全景 移 方觉明推门而入，反手关门落锁。 （无对白） 急促脚步声 8s
S01-6 特写 固定 方觉明的脸：瞳孔轻微放大，额角细密冷汗。 （无对白） 心跳声渐起 6s
S01-7 中景 固定 苏晚拔掉网线；方觉明同时拔掉主服务器网线。 方觉明："数据传上去没有？" 苏晚："只跑了本地比对" 插拔声 10s
S01-8 近景 推 方觉明转身握住苏晚的肩膀。 方觉明（一字一顿）："他们要找的人，终于出现了。" 警报骤响 8s
S01-13 中景 跟 苏晚转身就跑。身后传来三声被消音器压住的枪响。 （无对白） 闷响×3，铁门轰响 10s
S01-14 黑场 切 黑场中亮起手机屏幕：来电显示"妈妈家"。 字幕：魔都 · 凌晨四点四十二分。 （无对白） 手机振动声 6s
</section>
</body></html>
"""


def test_parse_html_sequences_and_shots():
    sb = parse_storyboard_html(HTML)
    assert len(sb.sequences) == 2
    seq0, seq1 = sb.sequences
    assert seq0["id"] == "seq-0"
    assert seq1["title"] == "第一章 · 垃圾DNA"
    assert len(seq0["shots"]) == 2
    assert len(seq1["shots"]) == 10
    assert seq1["shots"][0]["shot_id"] == "S01-1"
    assert seq1["shots"][0]["duration_s"] == 8.0


def test_shot_field_parsing():
    sb = parse_storyboard_html(HTML)
    plan = storyboard_to_plan("p", sb, max_shots=50)
    by_id = {s.id: s for s in plan.shots}
    s13 = by_id["S01-13"]
    # 动作镜：分类 + handoff
    assert s13.description.startswith("苏晚转身就跑")
    assert "gun" in s13.sfx or "impact" in s13.sfx
    assert len(s13.positive_prompt) > 50
    assert "mosaic" in s13.negative_prompt

    s1 = by_id["S01-1"]
    assert s1.duration == 8.0
    assert "push-in" in s1.camera

    # 台词镜：dialogue 被提取
    s7 = by_id["S01-7"]
    assert any("数据传上去没有" in d for d in s7.dialogue)

    # 情绪特写
    s3 = by_id["S01-3"]
    assert s3.motion_level >= 0


def test_storyboard_to_shot_dicts_handoff():
    sb = parse_storyboard_html(HTML)
    shots = storyboard_to_shot_dicts(sb)
    by_id = {s["id"]: s for s in shots}
    assert by_id["S01-13"]["handoff_mode"] == "continuous_action"
    assert by_id["S01-14"]["handoff_mode"] == "scene_change"
    assert by_id["S01-1"]["shot_class"] == "establishing"
    assert by_id["S01-3"]["shot_class"] == "emotion_closeup"


def test_load_storyboard_json(tmp_path):
    data = {
        "source": "test.html",
        "sequences": [
            {"id": "seq-0", "raw": "S00 序章", "shots": [
                {"shot_id": "S00-1", "duration_s": 8.0,
                 "content": "大远景 拉 黑场中，远古星图缓缓浮现。 旁白（低吟）：\"西北海之外\"。 低频轰鸣 8s"}
            ]},
        ],
    }
    path = tmp_path / "sb.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    sb = load_storyboard(path)
    assert sb.source == str(path)
    assert len(sb.all_shots()) == 1


def test_plan_shot_count_limit():
    sb = parse_storyboard_html(HTML)
    plan = storyboard_to_plan("p", sb, max_shots=3)
    assert len(plan.shots) == 3
    assert plan.shots[0].id == "S00-1"


def test_unsupported_format(tmp_path):
    path = tmp_path / "sb.txt"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        load_storyboard(path)
