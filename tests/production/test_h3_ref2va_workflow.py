import json
from pathlib import Path

from backend.production.workflow_templates import WorkflowTemplate


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "backend" / "production" / "workflows" / "h3" / "reference.json"
SCHEMA = ROOT / "backend" / "production" / "workflows" / "h3" / "reference.schema.json"


def test_reference_workflow_renders_three_picture_slots():
    template = WorkflowTemplate.load(WORKFLOW)

    rendered = template.render(
        prompt="继承 <Picture 1> 并继续前进",
        picture_1="tail.png",
        picture_2="character.png",
        picture_3="scene.png",
        ref_images=[["7", 0], ["8", 0], ["9", 0]],
        width=864,
        height=480,
        frames=124,
        steps=6,
        denoise=1.0,
        seed=42,
        fps=24,
        lora_strength=1.0,
        low_vram=False,
        shift_video=12.0,
        shift_audio=3.0,
        diffusion_model="minimax_h3_ref2va_pruned_int8_convrot.safetensors",
        text_encoder="qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        video_vae="minimax_h3_video_vae_fp16.safetensors",
        audio_vae="minimax_h3_audio_vae_fp32.safetensors",
        filename_prefix="AI_Manga_Studio/H3/test/s01",
    )

    assert rendered["15"]["inputs"]["ref_images"] == [["7", 0], ["8", 0], ["9", 0]]
    assert rendered["7"]["inputs"]["image"] == "tail.png"
    assert rendered["4"]["inputs"]["unet_name"].startswith("minimax_h3_ref2va")


def test_reference_workflow_matches_native_node_schema():
    template = WorkflowTemplate.load(WORKFLOW)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert set(template.workflow) == set(schema["nodes"])
    for node_id, expected in schema["nodes"].items():
        node = template.workflow[node_id]
        assert node["class_type"] == expected["class_type"]
        assert set(expected["required_inputs"]).issubset(node["inputs"])
