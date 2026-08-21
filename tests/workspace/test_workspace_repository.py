from backend.orchestration.database import OrchestrationDatabase
from backend.workspace.models import StageAutomation, StageKey
from backend.workspace.repository import WorkspaceRepository


def test_stage_automation_round_trips(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "workspace.db"))
    repo = WorkspaceRepository(db)
    value = StageAutomation(
        stage_key=StageKey.KEYFRAME,
        auto_produce=False,
        quality_threshold=0.82,
        max_quality_retries=2,
        auto_advance=False,
    )

    repo.upsert_stage_automation("gui-xu", value)

    assert repo.get_stage_automation("gui-xu", StageKey.KEYFRAME) == value


def test_all_stage_defaults_are_returned_in_fixed_order(tmp_path):
    repo = WorkspaceRepository(OrchestrationDatabase(str(tmp_path / "workspace.db")))

    values = repo.get_all_stage_automation("gui-xu")

    assert [value.stage_key for value in values] == list(StageKey)
    assert all(value.auto_produce is True for value in values)
    assert all(value.max_quality_retries == 2 for value in values)


def test_stage_settings_persist_across_repository_instances(tmp_path):
    db_path = str(tmp_path / "workspace.db")
    value = StageAutomation(
        stage_key=StageKey.VIDEO,
        quality_threshold=0.91,
        provider_settings={"provider": "comfy"},
    )

    WorkspaceRepository(OrchestrationDatabase(db_path)).upsert_stage_automation("gui-xu", value)
    restored = WorkspaceRepository(OrchestrationDatabase(db_path)).get_stage_automation(
        "gui-xu", StageKey.VIDEO
    )

    assert restored == value
