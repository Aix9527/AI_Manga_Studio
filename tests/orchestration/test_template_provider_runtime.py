import pytest


def _settings(mode: str, provider: str, fallback: str = "") -> dict:
    provider_policy = {"mode": mode, "provider": provider}
    if fallback:
        provider_policy["fallback"] = fallback
    return {
        "stage_policy": [
            {
                "stage_key": "video_generate",
                "enabled": True,
                "provider_policy": provider_policy,
            }
        ]
    }


def test_required_h3_runtime_plan_has_no_wan_fallback():
    from backend.orchestration.worker import resolve_video_provider_plan

    plan = resolve_video_provider_plan(_settings("required", "minimax_h3"))

    assert plan.providers == ("minimax_h3",)
    assert plan.required is True


def test_preferred_h3_runtime_plan_uses_only_explicit_wan_fallback():
    from backend.orchestration.worker import resolve_video_provider_plan

    plan = resolve_video_provider_plan(_settings("preferred", "minimax_h3", "wan"))

    assert plan.providers == ("minimax_h3", "wan")
    assert plan.required is False


def test_runtime_default_preserves_existing_wan_path():
    from backend.orchestration.worker import resolve_video_provider_plan

    plan = resolve_video_provider_plan({"stage_policy": []})

    assert plan.providers == ("wan",)
    assert plan.required is False


def test_required_flux_is_strict_for_visual_stage():
    from backend.orchestration.worker import stage_provider_is_required

    settings = {
        "stage_policy": [
            {
                "stage_key": "visual_generate",
                "enabled": True,
                "provider_policy": {"mode": "required", "provider": "flux"},
            }
        ]
    }

    assert stage_provider_is_required(settings, "visual_generate", "flux") is True


def test_compiler_rejects_provider_on_wrong_stage_and_unenforceable_cosyvoice():
    from backend.workspace.template_compiler import CanonicalTemplateCompiler, TemplateValidationError
    from tests.workspace.test_production_template_compiler import _default_template

    wrong_stage = _default_template()
    wrong_stage["stage_policy"] = {
        "stages": [
            {
                "stage_key": "video_generate",
                "provider_policy": {"mode": "required", "provider": "flux"},
            }
        ]
    }
    with pytest.raises(TemplateValidationError, match="provider"):
        CanonicalTemplateCompiler().compile(wrong_stage)

    audio = _default_template()
    audio["stage_policy"] = {
        "stages": [
            {
                "stage_key": "audio_tts",
                "provider_policy": {"mode": "required", "provider": "cosyvoice"},
            }
        ]
    }
    with pytest.raises(TemplateValidationError, match="provider"):
        CanonicalTemplateCompiler().compile(audio)
