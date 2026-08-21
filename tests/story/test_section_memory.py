from __future__ import annotations

from backend.story.models import Chapter, Scene
from backend.story.section_memory import StorySectionMemory


def test_build_section_visual_theme(tmp_path):
    mem = StorySectionMemory(storage_dir=tmp_path / "sections")
    chapter = Chapter(id="ch1", novel_id="novel_a", number=1, title="天倾")
    scene = Scene(
        id="sc1", chapter_id="ch1", number=1, title="实验室",
        location="京城大学基因考古实验室", mood="tense", characters=["苏晚", "陈夜"],
        tags=["lab"],
    )
    sec = mem.build_section(scene, chapter=chapter)
    assert sec.section_key == "ch1_sc01"
    assert sec.visual_theme["palette"] == "cold_blue"
    assert sec.emotion == "tense"
    assert "苏晚" in sec.character_state


def test_save_load_and_previous_event(tmp_path):
    mem = StorySectionMemory(storage_dir=tmp_path / "sections")
    c = Chapter(id="c1", novel_id="n1", number=1)
    s1 = Scene(id="s1", chapter_id="c1", number=1, title="警报", mood="dark", location="地下")
    s2 = Scene(id="s2", chapter_id="c1", number=2, title="遗迹", mood="calm", location="归墟遗迹", tags=["青铜"])
    first = mem.build_section(s1, chapter=c)
    mem.save("n1", first)
    second = mem.build_section(s2, chapter=c, prev_section=first)
    mem.save("n1", second)

    loaded = mem.load("n1", "ch1_sc02")
    assert loaded is not None
    assert loaded.previous_event == first.summary
    assert loaded.visual_theme["palette"] == "bronze_gold"

    ctx = mem.memory_context("n1", "ch1_sc02")
    assert ctx["available"] is True
    assert ctx["emotion"] == "calm"
    assert ctx["location"] == "归墟遗迹"


def test_list_sections_ordered(tmp_path):
    mem = StorySectionMemory(storage_dir=tmp_path / "sections")
    c = Chapter(id="c1", novel_id="n1", number=1)
    for num in (1, 2, 3):
        sc = Scene(id=f"s{num}", chapter_id="c1", number=num, title=f"场{num}")
        mem.save("n1", mem.build_section(sc, chapter=c))
    keys = [s.section_key for s in mem.list_sections("n1")]
    assert keys == ["ch1_sc01", "ch1_sc02", "ch1_sc03"]
