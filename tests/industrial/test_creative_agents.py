"""AI_Manga_Studio v1.0 Phase 2: Creative Agents tests. """

from __future__ import annotations

from backend.creative.agents import CreativeTeam


def test_writer_episode_structure():
    team = CreativeTeam()
    result = team.writer.write_episode(story="陈夜进入地下城", characters=["陈夜"])
    assert result["dramatic_structure"]["opening"] == "陈夜进入地下城"
    assert result["scenes"][0]["characters"] == ["陈夜"]
    assert "镜头化" in result or "shots" in result["scenes"][0]


def test_actor_expression_and_acting():
    team = CreativeTeam()
    result = team.actor.act(character="陈夜", emotion="恐惧")
    assert "subtle fear" in result["expression_prompt"]
    assert result["character_state"]["emotion"] == "恐惧"
    assert "连续自然表演" in result["acting_prompt"]


def test_camera_library():
    team = CreativeTeam()
    hero = team.camera.direct(mood="英雄登场")
    assert hero["shot_type"] == "low angle"
    assert hero["lens"] == "35mm"
    assert "backlight" in hero["lighting"]
    tense = team.camera.direct(mood="紧张")
    assert tense["shot_type"] == "handheld"


def test_motion_timeline():
    team = CreativeTeam()
    battle = team.motion.choreograph(action_type="战斗")
    assert battle["motion_timeline"][0] == "0-1s 拔剑"
    assert "dynamic continuous movement" in battle["motion_prompt"]


def test_art_style_dna():
    team = CreativeTeam()
    art = team.art.design()
    assert art["style_dna"]["color"] == "bronze + cyan"
    assert "no style drift" in art["style_prefix"]


def test_editor_and_sound():
    team = CreativeTeam()
    edit = team.editor.edit(mood="动作", shot_count=12)
    assert "3" in edit["shot_duration_rule"]
    sound = team.sound.sound(scene="地下城", emotion="紧张")
    assert "metal echo" in sound["sfx"]
    assert sound["bgm"] == "低频弦乐"


def test_shot_bible_collaboration():
    team = CreativeTeam()
    bible = team.produce_shot_bible(story="陈夜发现青铜门", characters=["陈夜"],
                                    emotion="好奇", mood="史诗", action_type="探索")
    assert bible["id"] == "gx001"
    assert bible["camera"]["shot_type"] == "crane shot"
    assert bible["acting"]["character"] == "陈夜"
    assert bible["motion"]["motion_timeline"]
    assert bible["art"]["style_dna"]["style"] == "cinematic realism"
