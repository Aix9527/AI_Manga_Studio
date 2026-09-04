import pytest


def _default_template() -> dict[str, object]:
    return {
        "schema_version": 1,
        "canvas": {
            "nodes": [
                {"id": "novel", "data": {"stageKey": "load_input"}},
                {"id": "scene", "data": {"stageKey": "planning"}},
                {"id": "character", "data": {"stageKey": "character_design"}},
                {"id": "storyboard", "data": {"stageKey": "planning"}},
                {"id": "keyframe", "data": {"stageKey": "visual_generate"}},
                {"id": "video", "data": {"stageKey": "video_generate"}},
                {"id": "audio", "data": {"stageKey": "audio_tts"}},
                {"id": "export", "data": {"stageKey": "composition_compose"}},
            ],
            "edges": [
                {"source": "novel", "target": "scene"},
                {"source": "scene", "target": "character"},
                {"source": "character", "target": "storyboard"},
                {"source": "storyboard", "target": "keyframe"},
                {"source": "keyframe", "target": "video"},
                {"source": "video", "target": "audio"},
                {"source": "audio", "target": "export"},
            ],
        },
        "production": {
            "shot_duration": 5,
            "width": 1080,
            "height": 1920,
            "fps": 24,
            "options": {"style": "anime", "local_first": True},
        },
        "stage_policy": {"stages": []},
    }


def test_default_canvas_compiles_and_folds_planning_aliases():
    from backend.workspace.template_compiler import CanonicalTemplateCompiler

    compiled = CanonicalTemplateCompiler().compile(_default_template())

    assert compiled["canonical_stages"].count("planning") == 1
    assert compiled["canonical_stages"] == [
        "load_input",
        "planning",
        "character_design",
        "visual_generate",
        "video_generate",
        "audio_tts",
        "composition_compose",
    ]


def test_unknown_executable_stage_fails_closed():
    from backend.workspace.template_compiler import CanonicalTemplateCompiler, TemplateValidationError

    value = _default_template()
    value["canvas"]["nodes"].append({"id": "shell", "data": {"stageKey": "run_shell"}})

    with pytest.raises(TemplateValidationError, match="unknown stage"):
        CanonicalTemplateCompiler().compile(value)


def test_reverse_dependency_between_distinct_canonical_stages_is_rejected():
    from backend.workspace.template_compiler import CanonicalTemplateCompiler, TemplateValidationError

    value = _default_template()
    value["canvas"]["edges"].append({"source": "video", "target": "keyframe"})

    with pytest.raises(TemplateValidationError, match="dependency"):
        CanonicalTemplateCompiler().compile(value)


def test_reverse_dependency_into_planning_alias_is_rejected():
    from backend.workspace.template_compiler import CanonicalTemplateCompiler, TemplateValidationError

    value = _default_template()
    value["canvas"]["edges"].append({"source": "video", "target": "scene"})

    with pytest.raises(TemplateValidationError, match="dependency"):
        CanonicalTemplateCompiler().compile(value)


def test_required_stage_cannot_be_disabled():
    from backend.workspace.template_compiler import CanonicalTemplateCompiler, TemplateValidationError

    value = _default_template()
    value["stage_policy"] = {"stages": [{"stage_key": "planning", "enabled": False}]}

    with pytest.raises(TemplateValidationError, match="required stage"):
        CanonicalTemplateCompiler().compile(value)


def test_required_h3_fails_when_runtime_capability_is_missing():
    from backend.workspace.template_compiler import CanonicalTemplateCompiler, TemplateValidationError

    value = _default_template()
    value["stage_policy"] = {
        "stages": [
            {
                "stage_key": "video_generate",
                "provider_policy": {"mode": "required", "provider": "minimax_h3"},
            }
        ]
    }

    with pytest.raises(TemplateValidationError, match="required provider"):
        CanonicalTemplateCompiler(available_providers={"wan", "flux", "cosyvoice"}).compile(value)


def test_preferred_provider_with_explicit_supported_fallback_is_allowed():
    from backend.workspace.template_compiler import CanonicalTemplateCompiler

    value = _default_template()
    value["stage_policy"] = {
        "stages": [
            {
                "stage_key": "video_generate",
                "provider_policy": {
                    "mode": "preferred",
                    "provider": "minimax_h3",
                    "fallback": "wan",
                },
            }
        ]
    }

    compiled = CanonicalTemplateCompiler(available_providers={"wan", "flux", "cosyvoice"}).compile(value)

    policy = next(item for item in compiled["stage_policy"] if item["stage_key"] == "video_generate")
    assert policy["provider_policy"]["fallback"] == "wan"


def test_qc_or_review_bypass_fields_are_rejected():
    from backend.workspace.template_compiler import CanonicalTemplateCompiler, TemplateValidationError

    value = _default_template()
    value["production"]["options"]["skip_qc"] = True

    with pytest.raises(TemplateValidationError, match="forbidden"):
        CanonicalTemplateCompiler().compile(value)
