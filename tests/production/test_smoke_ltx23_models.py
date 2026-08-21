from pathlib import Path

from scripts.smoke_local_media import require_ltx23_models


def test_ltx_smoke_preflight_accepts_split_models_without_full_checkpoint(
    tmp_path: Path,
    monkeypatch,
):
    relative_paths = [
        (
            "diffusion_models",
            "ltx-2.3-22b-distilled_transformer_only_fp8_input_scaled.safetensors",
        ),
        ("clip", "gemma_3_12B_it_fp4_mixed.safetensors"),
        ("clip", "ltx-2.3_text_projection_bf16.safetensors"),
        ("vae", "LTX23_video_vae_bf16.safetensors"),
    ]
    for parts in relative_paths:
        path = tmp_path.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"model")
    monkeypatch.setenv("LTX23_MODEL_ROOT", str(tmp_path))

    resolved = require_ltx23_models()

    assert set(resolved) == {
        "transformer",
        "text_encoder",
        "text_projection",
        "video_vae",
    }
