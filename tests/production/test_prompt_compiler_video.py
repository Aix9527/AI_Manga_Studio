from backend.production.contracts import ShotSpec
from backend.prompt_compiler.compiler import PromptCompiler


def test_video_prompt_compiler_adds_motion_and_stability_constraints():
    shot = ShotSpec(
        id="shot_001",
        shot_number=1,
        description="林舟回头望向实验室深处",
        camera="slow push-in, shallow depth of field",
        characters=["林舟"],
        positive_prompt="cinematic laboratory, emergency lights",
        negative_prompt="low quality",
    )

    compiled = PromptCompiler().compile_video_shot(shot)

    assert "slow push-in" in compiled.positive_prompt
    assert "smooth natural motion" in compiled.positive_prompt
    assert "林舟回头望向实验室深处" in compiled.positive_prompt
    assert "jitter" in compiled.negative_prompt
    assert "identity drift" in compiled.negative_prompt
    assert compiled.target_node == "WanVideoTextEncode"
