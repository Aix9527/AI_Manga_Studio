import pytest

from backend.orchestration.database import OrchestrationDatabase
from backend.workspace.repository import WorkspaceRepository


def _repo(tmp_path):
    return WorkspaceRepository(OrchestrationDatabase(str(tmp_path / "workspace.db")))


def _version_payload(name: str = "默认模板") -> dict[str, object]:
    return {
        "name": name,
        "schema_version": 1,
        "content_json": '{"schema_version":1,"canvas":{"nodes":[],"edges":[]}}',
        "content_sha256": "source-hash",
        "compiled_json": '{"production":{"width":1080}}',
        "compiled_sha256": "compiled-hash",
    }


def test_first_and_sequential_saves_create_immutable_versions(tmp_path):
    repo = _repo(tmp_path)

    first = repo.save_production_template_version("project-a", _version_payload("v1"))
    second = repo.save_production_template_version("project-a", _version_payload("v2"))

    assert first.version == 1
    assert second.version == 2
    assert repo.get_production_template_version("project-a", 1).name == "v1"
    assert repo.get_production_template_version("project-a", 2).name == "v2"


def test_project_versions_are_isolated(tmp_path):
    repo = _repo(tmp_path)

    a = repo.save_production_template_version("project-a", _version_payload("A"))
    b = repo.save_production_template_version("project-b", _version_payload("B"))

    assert a.version == 1
    assert b.version == 1
    assert repo.get_production_template_version("project-a", 1).name == "A"
    assert repo.get_production_template_version("project-b", 1).name == "B"


def test_publish_pointer_can_roll_back_to_older_version(tmp_path):
    repo = _repo(tmp_path)
    repo.save_production_template_version("project-a", _version_payload("v1"))
    repo.save_production_template_version("project-a", _version_payload("v2"))

    published_v2 = repo.publish_production_template("project-a", 2)
    published_v1 = repo.publish_production_template("project-a", 1)

    assert published_v2.version == 2
    assert published_v1.version == 1
    assert repo.get_published_production_template("project-a").version == 1


def test_published_version_cannot_be_archived(tmp_path):
    repo = _repo(tmp_path)
    repo.save_production_template_version("project-a", _version_payload("v1"))
    repo.publish_production_template("project-a", 1)

    with pytest.raises(ValueError, match="published"):
        repo.set_production_template_archived("project-a", 1, True)


def test_list_reports_latest_and_published_versions(tmp_path):
    repo = _repo(tmp_path)
    repo.save_production_template_version("project-a", _version_payload("v1"))
    repo.save_production_template_version("project-a", _version_payload("v2"))
    repo.publish_production_template("project-a", 1)

    state = repo.list_production_template_versions("project-a")

    assert state.latest_version == 2
    assert state.published_version == 1
    assert [item.version for item in state.versions] == [2, 1]
