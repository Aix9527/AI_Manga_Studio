from backend.production.hd_redraw import build_keyframe_refine_prompt


def test_keyframe_refine_prompt_preserves_composition_and_adds_detail():
    prompt = build_keyframe_refine_prompt("林舟站在黑色巨门前，海风吹动衣角")

    assert "preserve the exact composition" in prompt
    assert "preserve character identity" in prompt
    assert "ultra high definition" in prompt
    assert "林舟站在黑色巨门前" in prompt
