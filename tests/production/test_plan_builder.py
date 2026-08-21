import json
from pathlib import Path

from backend.production.contracts import Chapter, InputContract, InputType, LoadedInput
from backend.production.plan_builder import PlanSettings, build_trailer_plan, save_plan


def _loaded_input() -> LoadedInput:
    short_heading = Chapter(index=1, title="第一部分：末日序幕", content="卷标题", word_count=3)
    story = (
        "实验室的警报突然响起。林舟看见培养舱中的海水逆流，"
        "失踪多年的父亲从监控画面中抬起头。整座城市同时停电，"
        "远处海面升起一扇横跨天际的黑色巨门。"
    ) * 80
    chapter = Chapter(index=2, title="第一节 基因DNA", content=story, word_count=len(story))
    contract = InputContract(path="book.txt", type=InputType.NOVEL, title="归墟")
    return LoadedInput(contract=contract, text=story, chapters=[short_heading, chapter])


def test_trailer_plan_is_vertical_live_action_and_within_duration():
    plan = build_trailer_plan(
        "gui-xu",
        _loaded_input(),
        PlanSettings(target_seconds=60, max_shots=10, width=1080, height=1920),
    )

    assert plan.settings["style"] == "live_action_cinematic"
    assert plan.settings["generation_width"] == 480
    assert plan.settings["generation_height"] == 832
    assert 8 <= len(plan.shots) <= 10
    assert 50 <= plan.total_duration <= 70
    assert all("anime" not in shot.positive_prompt.lower() for shot in plan.shots)
    assert all("manga" in shot.negative_prompt.lower() for shot in plan.shots)
    assert all(shot.narration for shot in plan.shots)


def test_plan_round_trips_as_utf8_json(tmp_path: Path):
    plan = build_trailer_plan("gui-xu", _loaded_input(), PlanSettings())
    output = save_plan(plan, tmp_path / "production_plan.json")

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["project_id"] == "gui-xu"
    assert payload["shots"][0]["id"] == "shot_01"
    assert payload["settings"]["provider"] == "ltx23"
