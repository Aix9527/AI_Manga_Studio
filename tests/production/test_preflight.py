import pytest

from backend.production.preflight import inspect_object_info


def h3_object_info() -> dict:
    return {
        "UNETLoader": {
            "input": {"required": {"unet_name": [[
                "MiniMax-H3/minimax_h3_ref2va_pruned_int8_convrot.safetensors"
            ]]}}
        },
        "CLIPLoader": {
            "input": {"required": {"clip_name": [[
                "Qwen/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
            ]]}}
        },
        "VAELoader": {
            "input": {"required": {"vae_name": [[
                "vae/minimax_h3_video_vae_fp16.safetensors",
                "vae/minimax_h3_audio_vae_fp32.safetensors",
            ]]}}
        },
        "MiniMaxH3ReferenceToVideo": {
            "input": {"required": {
                "clip": ["CLIP"], "vae": ["VAE"], "audio_vae": ["VAE"],
                "prompt": ["STRING"], "width": ["INT"], "height": ["INT"],
                "length": ["INT"], "ref_image_size": ["STRING"], "ref_images": ["IMAGE"], "ref_videos": ["VIDEO"],
                "ref_video_audios": ["AUDIO"], "ref_audios": ["AUDIO"],
            }}
        },
        "VAEDecodeAudio": {"input": {"required": {"samples": ["LATENT"], "vae": ["VAE"]}}},
        "CreateVideo": {"input": {"required": {
            "images": ["IMAGE"], "audio": ["AUDIO"], "fps": ["INT"], "bit_depth": ["INT"],
        }}},
        "SaveVideo": {"input": {"required": {
            "video": ["VIDEO"], "filename_prefix": ["STRING"], "format": ["STRING"], "codec": ["STRING"],
        }}},
    }


def test_ltx_preflight_requires_model_encoder_vae_and_save_node():
    report = inspect_object_info(
        {
            "UNETLoader": {
                "input": {"required": {"unet_name": [["ltx-2.3-22b-distilled-fp8.safetensors"]]}}
            },
            "CLIPLoader": {
                "input": {"required": {"clip_name": [["ltx-2.3_text_projection_bf16.safetensors"]]}}
            },
            "VAELoader": {
                "input": {"required": {"vae_name": [["LTX23_video_vae_bf16.safetensors"]]}}
            },
            "SaveVideo": {"input": {"required": {}}},
        },
        provider="ltx23",
    )

    assert report.ok is True
    assert report.missing == []


def test_wan_preflight_names_missing_high_noise_model():
    report = inspect_object_info(
        {
            "UNETLoader": {
                "input": {
                    "required": {
                        "unet_name": [
                            ["Wan2.2/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"]
                        ]
                    }
                }
            },
            "CLIPLoader": {
                "input": {"required": {"clip_name": [["umt5_xxl_fp8_e4m3fn_scaled.safetensors"]]}}
            },
            "VAELoader": {
                "input": {"required": {"vae_name": [["wan2.2_vae.safetensors"]]}}
            },
            "SaveVideo": {"input": {"required": {}}},
        },
        provider="wan22",
    )

    assert report.ok is False
    assert "wan_high_noise_model" in report.missing


def test_h3_preflight_resolves_roles_without_exact_filename():
    """Catch a preflight that hard-codes one local H3 model pathname."""
    report = inspect_object_info(h3_object_info(), provider="minimax_h3_ref2va")

    assert report.ok is True
    assert report.resolved["diffusion_model"].endswith("ref2va_pruned_int8_convrot.safetensors")
    assert report.resolved["text_encoder"].endswith("minimax_h3_nvfp4_awq.safetensors")
    assert report.resolved["video_vae"].endswith("minimax_h3_video_vae_fp16.safetensors")
    assert report.resolved["audio_vae"].endswith("minimax_h3_audio_vae_fp32.safetensors")


@pytest.mark.parametrize("input_name", ["ref_images", "ref_image_size"])
def test_h3_preflight_rejects_missing_native_reference_input(input_name: str):
    """Catch a native H3 node that cannot accept the approved reference-image contract."""
    object_info = h3_object_info()
    del object_info["MiniMaxH3ReferenceToVideo"]["input"]["required"][input_name]

    report = inspect_object_info(object_info, provider="minimax_h3_ref2va")

    assert report.ok is False
    assert "h3_reference_to_video" in report.missing


def test_h3_preflight_rejects_wrong_native_reference_descriptor():
    """Catch object_info that has the right input name but cannot carry image references."""
    object_info = h3_object_info()
    object_info["MiniMaxH3ReferenceToVideo"]["input"]["required"]["ref_images"] = ["STRING"]

    report = inspect_object_info(object_info, provider="minimax_h3_ref2va")

    assert report.ok is False
    assert "h3_reference_to_video" in report.missing
    assert "ref_images" in next(check.detail for check in report.checks if check.name == "h3_reference_to_video")


def test_h3_preflight_reports_ambiguous_models_without_dict_order_selection():
    """Catch an installed-model chooser that silently depends on object_info insertion order."""
    object_info = h3_object_info()
    object_info["UNETLoader"]["input"]["required"]["unet_name"] = [[
        "z/minimax_h3_ref2va_pruned_int8_convrot.safetensors",
        "a/minimax_h3_ref2va_pruned_int8_convrot.safetensors",
    ]]

    report = inspect_object_info(object_info, provider="minimax_h3_ref2va")

    assert report.ok is False
    assert report.resolved["diffusion_model"] == ""
    assert set(report.resolved) == {"diffusion_model", "text_encoder", "video_vae", "audio_vae"}
    assert report.ambiguities["diffusion_model"] == [
        "a/minimax_h3_ref2va_pruned_int8_convrot.safetensors",
        "z/minimax_h3_ref2va_pruned_int8_convrot.safetensors",
    ]
