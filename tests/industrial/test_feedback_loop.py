"""Phase 13.4-C: Asset Feedback Loop tests (event -> candidate -> review -> apply)."""

from __future__ import annotations

import pytest

from backend.characters.bible_v2.service import CharacterBibleService
from backend.feedback.service import FeedbackService
from backend.prompt_intelligence.service import PromptIntelligenceService
from backend.shot_dna.library import ShotDNALibrary
from backend.world.service import WorldService


@pytest.fixture()
def feedback(tmp_path):
    return FeedbackService(
        str(tmp_path / "fb"),
        characters=CharacterBibleService(str(tmp_path / "bible")),
        world=WorldService(str(tmp_path / "world")),
        shot_dna=ShotDNALibrary(str(tmp_path / "dna.json")),
        intelligence=PromptIntelligenceService(str(tmp_path / "pi")),
        min_samples=10, prior_weight=5,
    )


def test_record_and_list_event(feedback):
    event = feedback.record_event(
        kind="critic", target_type="character", target_id="CH-001",
        source="vision_critic", severity="high", issues=["expression_forced", "side_view_identity_drift"],
        metrics={"score": 0.62},
    )
    assert event["issues"] == ["expression_forced", "side_view_identity_drift"]
    rows = feedback.list_events(target_type="character")
    assert len(rows) == 1
    assert feedback.stats()["events"] == 1


def test_invalid_event_rejected(feedback):
    with pytest.raises(ValueError, match="invalid event kind"):
        feedback.record_event(kind="unknown", target_type="character", target_id="CH-001")


def test_shot_outcome_stats_and_min_sample_gate(feedback):
    dna = feedback.shot_dna.all()[0]
    for i in range(4):
        feedback.record_shot_outcome(dna.id, success=True, quality=0.9, human_score=8.0)
    stats = feedback.shot_stats(dna.id)
    assert stats["usage_count"] == 4
    assert stats["success_count"] == 4
    assert stats["avg_quality"] == 0.9
    # below min_samples -> no candidate proposed
    assert feedback.auto_propose(min_samples=10) == []
    for i in range(6):
        feedback.record_shot_outcome(dna.id, success=False, quality=0.5, human_score=5.0)
    stats = feedback.shot_stats(dna.id)
    assert stats["usage_count"] == 10
    assert stats["success_count"] == 4
    candidates = feedback.auto_propose(min_samples=10)
    assert len(candidates) == 1
    assert candidates[0]["target_type"] == "shot_dna"
    assert candidates[0]["status"] == "proposed"


def test_candidate_review_and_apply_shot_dna(feedback):
    dna = feedback.shot_dna.all()[0]
    for i in range(10):
        feedback.record_shot_outcome(dna.id, success=True, quality=0.9)
    candidates = feedback.auto_propose(min_samples=10)
    candidate = candidates[0]
    with pytest.raises(ValueError, match="only approved"):
        feedback.apply_candidate(candidate["id"])
    reviewed = feedback.review_candidate(candidate["id"], "approve", reviewer="制片人")
    assert reviewed["status"] == "approved"
    applied = feedback.apply_candidate(candidate["id"])
    assert applied["status"] == "applied"
    updated = feedback.shot_dna.get(dna.id)
    assert updated.usage_count == dna.usage_count + 10
    assert updated.success_rate > dna.success_rate


def test_character_issues_produce_new_version(feedback):
    feedback.characters.create("CH-001", name="苏晚")
    feedback.characters.add_version("CH-001", "v1", approved=True)
    feedback.characters.set_version_status("CH-001", "v1", approved=True, locked=True)
    for i in range(10):
        feedback.record_event(
            kind="identity_gate", target_type="character", target_id="CH-001",
            issues=["expression_forced"], severity="medium",
        )
    candidates = feedback.auto_propose(min_samples=10)
    assert len(candidates) == 1
    feedback.review_candidate(candidates[0]["id"], "approve", reviewer="导演")
    applied = feedback.apply_candidate(candidates[0]["id"])
    assert applied["status"] == "applied"
    bible = feedback.characters.get("CH-001")
    assert len(bible.versions) == 2
    new_version = [v for v in bible.versions.values() if v.id.startswith("fb-")][0]
    assert "expression_forced" in new_version.notes
    # locked v1 untouched
    assert bible.versions["v1"].locked is True


def test_prompt_feedback_creates_draft_version(feedback):
    row = feedback.intelligence.create_template(name="shot_lang", kind="shot", base_template="{prompt_template}")
    feedback.intelligence.set_version_status(row["id"], "v1", "approved")
    feedback.intelligence.set_version_status(row["id"], "v1", "locked")
    for i in range(10):
        feedback.record_event(
            kind="critic", target_type="prompt_template", target_id=row["id"],
            issues=["overacting"], severity="low",
        )
    candidates = feedback.auto_propose(min_samples=10)
    assert len(candidates) == 1
    feedback.review_candidate(candidates[0]["id"], "approve", reviewer="导演")
    feedback.apply_candidate(candidates[0]["id"])
    versions = feedback.intelligence.list_versions(row["id"])
    assert len(versions) == 2
    new_version = versions[-1]
    assert new_version["version_id"] == "v2"
    assert new_version["status"] == "draft"  # still needs human approval
    assert "overacting" in new_version["notes"]


def test_reject_candidate_keeps_assets(feedback):
    feedback.characters.create("CH-001", name="苏晚")
    for i in range(10):
        feedback.record_event(kind="critic", target_type="character", target_id="CH-001", issues=["side_view_identity_drift"])
    candidates = feedback.auto_propose(min_samples=10)
    feedback.review_candidate(candidates[0]["id"], "reject", reviewer="导演")
    assert feedback.store.get_candidate(candidates[0]["id"]).status == "rejected"
    with pytest.raises(ValueError, match="only approved"):
        feedback.apply_candidate(candidates[0]["id"])