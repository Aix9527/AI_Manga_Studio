"""Phase 13.4-A: Prompt Intelligence tests (versioning / review / A/B / compose)."""

from __future__ import annotations

import pytest

from backend.characters.bible_v2.service import CharacterBibleService
from backend.prompt_intelligence.composer import PromptComposer
from backend.prompt_intelligence.service import PromptIntelligenceService
from backend.shot_dna.library import ShotDNALibrary
from backend.world.service import WorldService


@pytest.fixture()
def service(tmp_path):
    return PromptIntelligenceService(str(tmp_path / "pi"))


@pytest.fixture()
def composer(tmp_path, service):
    return PromptComposer(
        intelligence=service,
        characters=CharacterBibleService(str(tmp_path / "bible")),
        world=WorldService(str(tmp_path / "world")),
        shot_dna=ShotDNALibrary(str(tmp_path / "dna.json")),
    )


def _template(service, name="character_portrait", kind="character", base="portrait of {character_name}, {appearance}"):
    return service.create_template(
        name=name, kind=kind, base_template=base,
        negative_prompt="low quality, blurry",
        quality_tags="masterpiece, best quality",
        variables=["character_name", "appearance"],
    )


def test_create_template_and_list(service):
    _template(service)
    row = service.get_template(service.list_templates()[0]["id"])
    assert row["kind"] == "character"
    assert row["active_version"] == ""
    assert len(row["versions"]) == 1
    assert row["versions"][0]["version_id"] == "v1"
    assert row["versions"][0]["status"] == "draft"
    assert row["versions"][0]["content_hash"]
    assert service.stats()["templates"] == 1


def test_duplicate_template_name_rejected(service):
    _template(service)
    with pytest.raises(ValueError, match="already exists"):
        _template(service)


def test_version_auto_numbering_and_parent(service):
    template = _template(service, base="v1 base")
    template_id = template["id"]
    service.create_version(template_id, base_template="v2 base")
    versions = service.list_versions(template_id)
    assert [v["version_id"] for v in versions] == ["v1", "v2"]
    assert versions[1]["parent_version"] == "v1"


def test_diff_versions(service):
    template = _template(service, base="v1 base")
    template_id = template["id"]
    service.create_version(template_id, base_template="v2 changed")
    diff = service.diff_versions(template_id, "v1", "v2")
    assert diff["changed"] is True
    assert any("v2 changed" in line for line in diff["diff"])


def test_version_status_workflow(service):
    template = _template(service)
    template_id = template["id"]
    with pytest.raises(ValueError, match="must be approved"):
        service.set_version_status(template_id, "v1", "locked")
    service.set_version_status(template_id, "v1", "approved", approved_by="导演")
    service.set_version_status(template_id, "v1", "locked")
    row = service.get_template(template_id)
    assert row["active_version"] == "v1"
    assert row["versions"][0]["status"] == "locked"


def test_review_approval_auto_approves(service):
    template = _template(service)
    template_id = template["id"]
    review = service.add_review(template_id, "v1", reviewer="制片人", status="approved", comments="OK")
    assert review["status"] == "approved"
    assert review["resolved_at"]
    assert service.list_versions(template_id)[0]["status"] == "approved"


def test_ab_test_lifecycle(service):
    template = _template(service)
    template_id = template["id"]
    service.create_version(template_id, base_template="variant base")
    ab = service.create_ab_test(template_id, "v1", "v2", name="portrait A/B")
    ab_id = ab["id"]
    assert ab["status"] == "running"
    for i in range(3):
        service.record_ab_result(ab_id, "base", success=True)
    for i in range(3):
        service.record_ab_result(ab_id, "variant", success=False)
    decided = service.decide_ab(ab_id)
    assert decided["status"] == "completed"
    assert decided["winner"] == "base"
    assert decided["results"]["base"]["score"] == 1.0


def test_ab_test_requires_samples(service):
    template = _template(service)
    template_id = template["id"]
    service.create_version(template_id, base_template="variant base")
    ab = service.create_ab_test(template_id, "v1", "v2")
    with pytest.raises(ValueError, match="not ready"):
        service.decide_ab(ab["id"])


def test_compose_character_uses_locked_template(service, composer):
    _template(service, base="portrait of {character_name}, {appearance}, quality {quality_tags}")
    template_id = service.list_templates()[0]["id"]
    service.set_version_status(template_id, "v1", "approved")
    service.set_version_status(template_id, "v1", "locked")
    composer.characters.create("CH-001", name="陈夜", age=24, gender="男")
    composer.characters.add_view("CH-001", "front", prompt="front view asset")
    result = composer.compose_character("CH-001", asset_type="view", asset_key="front")
    assert result["version_id"] == "v1"
    assert "陈夜" in result["positive_prompt"]
    assert "front" in result["positive_prompt"]
    assert "low quality" in result["negative_prompt"]


def test_compose_character_missing_bible(composer):
    with pytest.raises(KeyError, match="bible not found"):
        composer.compose_character("CH-MISSING")


def test_compose_world(service, composer):
    _template(service, name="world_bible_prompt", kind="world", base="world {world_name} {era} forbidden: {forbidden_elements}")
    world = composer.world.create_world("PROJ-W", name="归墟", era="未来科幻")
    composer.world.create_scene("PROJ-W", world_id=world.id, name="祭坛", forbidden_elements=["现代建筑"])
    result = composer.compose_world(project_id="PROJ-W")
    assert result["kind"] == "world"
    assert "归墟" in result["positive_prompt"]
    assert "现代建筑" in result["positive_prompt"]


def test_compose_shot_by_id_and_features(service, composer):
    _template(service, name="shot_language_prompt", kind="shot", base="{prompt_template}, {camera}, {lighting}")
    library = composer.shot_dna
    dna = library.all()[0]
    by_id = composer.compose_shot(dna_id=dna.id)
    assert by_id["source_id"] == dna.id
    assert dna.prompt_template or dna.scene in by_id["positive_prompt"]
    by_features = composer.compose_shot(features={"category": dna.category})
    assert by_features["source_id"] == dna.id


def test_compose_shot_missing(composer):
    with pytest.raises(KeyError, match="shot dna not found"):
        composer.compose_shot(dna_id="dna_does_not_exist", features={})


def test_legacy_compiler_bridge_exposes_approved_only(service):
    from backend.prompt_compiler.compiler import PromptCompiler
    from backend.prompt_intelligence.bridge import bridge_compiler

    row = service.create_template(name="shot_cinematic_bridge", kind="shot", base_template="cinematic {camera}")
    # draft only -> NOT bridged
    compiler = bridge_compiler(PromptCompiler(), service)
    assert "shot_cinematic_bridge" not in compiler.templates
    # approved -> bridged
    service.set_version_status(row["id"], "v1", "approved", approved_by="导演")
    compiler = bridge_compiler(PromptCompiler(), service)
    assert "shot_cinematic_bridge" in compiler.templates
    assert "cinematic {camera}" in compiler.templates["shot_cinematic_bridge"].base_template


def test_delete_template_rollback(service):
    template = _template(service)
    template_id = template["id"]
    service.add_review(template_id, "v1", reviewer="制片人", status="approved")
    assert service.delete_template(template_id) is True
    assert service.list_templates() == []
    with pytest.raises(KeyError):
        service.get_template(template_id)
    assert service.stats()["templates"] == 0
    assert service.list_reviews(template_id=template_id) == []