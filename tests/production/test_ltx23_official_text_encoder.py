from pathlib import Path

from backend.production.workflow_templates import WorkflowTemplate
from scripts.smoke_local_media import LTX23_MODELS


def test_ltx23_defaults_to_official_gemma_fp4_text_encoder():
    root = Path(__file__).resolve().parents[2]
    template = WorkflowTemplate.load(
        root / "backend" / "production" / "workflows" / "ltx23_i2v.json"
    )

    assert LTX23_MODELS["text_encoder"] == (
        "clip",
        "gemma_3_12B_it_fp4_mixed.safetensors",
    )
    assert template.workflow["4"]["inputs"]["text_encoder"] == (
        "gemma_3_12B_it_fp4_mixed.safetensors"
    )
