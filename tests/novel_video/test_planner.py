from dataclasses import FrozenInstanceError

import pytest

from backend.novel_video.planner import ChapterPlanner
from backend.production.contracts import Chapter, InputContract, InputType, LoadedInput


@pytest.fixture
def loaded_novel() -> LoadedInput:
    content = (
        "暮色压在荒原上，沈砚提着湿透的灯笼走向废弃驿站。"
        "他在门缝里听见妹妹的求救声，却发现地面留着陌生人的血脚印。"
        "暴雨突然熄灭了灯火，黑衣人从屋顶跃下，逼他交出铜钥匙。"
        "沈砚假意后退，把铜钥匙抛进井里，趁黑衣人扑向井口时撞开侧门。"
        "驿站外的雾中传来马蹄声，妹妹的声音却从井底再次响起。"
    )
    chapter = Chapter(index=1, title="第一章 雨夜驿站", content=content, word_count=len(content))
    return LoadedInput(
        contract=InputContract(path="story.txt", type=InputType.NOVEL, title="贪狼"),
        text=content,
        chapters=[chapter],
    )


def test_sixty_second_plan_uses_selected_chapter_not_fixed_demo(loaded_novel):
    bundle = ChapterPlanner().plan(
        loaded_novel,
        chapter_indexes=[1],
        target_seconds=60,
        max_shots=10,
    )

    assert 1 <= len(bundle.shots) <= 10
    assert sum(shot.duration_seconds for shot in bundle.shots) <= 60
    assert all(shot.source_excerpt in loaded_novel.chapters[0].content for shot in bundle.shots)
    assert {shot.narrative_purpose for shot in bundle.shots} >= {
        "opening",
        "conflict",
        "turn",
        "cliffhanger",
    }
    assert tuple(shot.sequence for shot in bundle.shots) == tuple(range(1, len(bundle.shots) + 1))
    assert bundle.plan_version


def test_user_limits_override_default_sixty_second_shot_suggestion(loaded_novel):
    bundle = ChapterPlanner().plan(
        loaded_novel,
        chapter_indexes=[1],
        target_seconds=25,
        max_shots=3,
    )

    assert len(bundle.shots) <= 3
    assert sum(shot.duration_seconds for shot in bundle.shots) <= 25


def test_plan_contracts_are_immutable_and_continuity_ready(loaded_novel):
    bundle = ChapterPlanner().plan(loaded_novel, chapter_indexes=[1], target_seconds=60)

    with pytest.raises(FrozenInstanceError):
        bundle.shots[0].prompt = "changed"
    assert bundle.shots[0].continuity == "location_jump"
    assert all(shot.continuity in {"same_action", "same_character_new_scene", "time_jump", "location_jump"} for shot in bundle.shots)


def test_repeated_excerpts_keep_selected_chapter_provenance_and_reset_tail():
    repeated = "雨夜里，沈砚听见井底传来妹妹的声音。"
    first = Chapter(index=1, title="第一章", content=repeated + "他握紧灯笼。", word_count=20)
    second = Chapter(index=2, title="第二章", content=repeated + "雾中传来马蹄声。", word_count=20)
    loaded = LoadedInput(
        contract=InputContract(path="story.txt", type=InputType.NOVEL, title="贪狼"),
        text=first.content + "\n" + second.content,
        chapters=[first, second],
    )

    bundle = ChapterPlanner().plan(
        loaded, chapter_indexes=[1, 2], target_seconds=30, max_shots=6
    )

    first_shot_by_chapter = {
        scene.chapter_index: scene.shots[0]
        for scene in bundle.scenes
        if scene.chapter_index not in {previous.chapter_index for previous in bundle.scenes[:bundle.scenes.index(scene)]}
    }
    assert [scene.chapter_index for scene in bundle.scenes] == [1, 1, 2, 2]
    assert first_shot_by_chapter[1].source_excerpt == repeated
    assert first_shot_by_chapter[2].source_excerpt == repeated
    assert first_shot_by_chapter[1].continuity == "location_jump"
    assert first_shot_by_chapter[2].continuity == "location_jump"
    assert not first_shot_by_chapter[1].inherit_tail
    assert not first_shot_by_chapter[2].inherit_tail
    assert bundle.scenes[2].shots[0].source_excerpt in second.content


def test_target_shorter_than_one_h3_segment_is_rejected(loaded_novel):
    with pytest.raises(ValueError, match="at least 5 seconds"):
        ChapterPlanner().plan(loaded_novel, chapter_indexes=[1], target_seconds=4)
