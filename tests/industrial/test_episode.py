"""Phase 13.1: Episode state machine + audit + rollback tests."""

from __future__ import annotations

import pytest

from backend.story.episode.model import Episode
from backend.story.episode.repository import EpisodeRepository
from backend.story.episode.service import EpisodeService
from backend.story.episode.state_machine import EpisodeState, EpisodeStateMachine


@pytest.fixture()
def service(tmp_path):
    repo = EpisodeRepository(str(tmp_path / "episodes.db"))
    return EpisodeService(repo)


def test_create_episode_starts_draft(service):
    episode = service.create("PROJ-1", episode_no=1, title="第一集")
    assert episode.status == EpisodeState.DRAFT.value
    assert episode.project_id == "PROJ-1"
    assert episode.episode_no == 1
    assert episode.title == "第一集"


def test_forward_transitions_full_lifecycle(service):
    episode = service.create("PROJ-1", episode_no=1)
    expected = [
        "planning", "script_ready", "storyboard_ready", "asset_ready",
        "production", "review", "approved", "published",
    ]
    for status in expected:
        episode = service.transition(episode.id, status, operator="dashboard")
    assert episode.status == "published"
    assert episode.production_progress == 1.0
    assert episode.approved_at
    assert episode.published_at


def test_illegal_jump_rejected(service):
    episode = service.create("PROJ-1", episode_no=1)
    with pytest.raises(ValueError):
        service.transition(episode.id, "published", operator="dashboard")
    assert service.get(episode.id).status == "draft"


def test_illegal_backward_jump_without_rollback(service):
    episode = service.create("PROJ-1", episode_no=1)
    service.transition(episode.id, "planning")
    with pytest.raises(ValueError):
        service.transition(episode.id, "draft")  # must use rollback()


def test_rollback_recovers_previous_state(service):
    episode = service.create("PROJ-1", episode_no=1)
    service.transition(episode.id, "planning")
    service.transition(episode.id, "script_ready")
    episode = service.rollback(episode.id, operator="dashboard")
    assert episode.status == "planning"
    # forward again to published, then rollback allowed
    for status in ["script_ready", "storyboard_ready", "asset_ready", "production", "review", "approved", "published"]:
        episode = service.transition(episode.id, status)
    episode = service.rollback(episode.id)
    assert episode.status == "approved"


def test_rollback_at_initial_state_fails(service):
    episode = service.create("PROJ-1", episode_no=1)
    with pytest.raises(ValueError):
        service.rollback(episode.id)


def test_audit_chain_records_every_action(service):
    episode = service.create("PROJ-1", episode_no=1)
    service.update_plan(episode.id, hook="开局冲突", conflict="被追杀", operator="planner")
    service.transition(episode.id, "planning")
    service.transition(episode.id, "script_ready")
    service.rollback(episode.id, operator="dashboard")
    entries = service.audit(episode.id)
    actions = [e["action"] for e in entries]
    assert "episode_create" in actions
    assert "episode_plan_update" in actions
    assert "episode_forward" in actions
    assert "episode_rollback" in actions
    # append-only: every entry has timestamps and operators
    assert all(e["created_at"] for e in entries)
    rollback_entries = [e for e in entries if e["action"] == "episode_rollback"]
    assert rollback_entries and rollback_entries[-1]["operator"] == "dashboard"


def test_state_machine_helpers():
    assert EpisodeStateMachine.allowed("draft", "planning") is True
    assert EpisodeStateMachine.allowed("draft", "published") is False
    assert EpisodeStateMachine.next_of("asset_ready") == "production"
    assert EpisodeStateMachine.previous_of("approved") == "review"
    assert EpisodeStateMachine.validate_transition("review", "production") == "rework"


def test_episode_plan_fields_persisted(service):
    episode = service.create("PROJ-1", episode_no=1)
    episode = service.update_plan(
        episode.id, hook="3秒冲突", conflict="身份揭露", climax="能力展示",
        ending="悬念", retention_strategy="cliffhanger", script_version="v1",
    )
    assert episode.hook == "3秒冲突"
    assert episode.conflict == "身份揭露"
    assert episode.climax == "能力展示"
    assert episode.ending == "悬念"
    assert episode.retention_strategy == "cliffhanger"
    assert episode.script_version == "v1"
    reloaded = service.get(episode.id)
    assert reloaded.hook == "3秒冲突"


def test_project_summary_counts_by_status(service):
    for no in range(1, 4):
        ep = service.create("PROJ-2", episode_no=no)
        if no == 2:
            service.transition(ep.id, "planning")
    summary = service.summary("PROJ-2")
    assert summary["total"] == 3
    assert summary["by_status"]["draft"] == 2
    assert summary["by_status"]["planning"] == 1
