"""Phase 12.9-A/D: Production Governance + Freeze tests (hermetic)."""

from __future__ import annotations

from pathlib import Path

from backend.governance import (
    ArtifactSigner,
    AuditLog,
    ReleaseManager,
    VersionRegistry,
    content_hash,
)
from backend.governance.production_freeze import ProductionFreeze


def _manager(tmp_path) -> ReleaseManager:
    return ReleaseManager(
        VersionRegistry(tmp_path / "vr.json"),
        AuditLog(tmp_path / "al.json"),
        ArtifactSigner(tmp_path / "release"),
    )


# ------------------------------------------------------------ manifest
def test_manifest_matches_gpt_signature_shape():
    manager = _manager(Path("."))
    manifest = manager.build_manifest()
    assert manifest["project"] == "归墟觉醒·天倾"
    assert manifest["pipeline"] == "v12.9"
    assert manifest["director"] == "council-v1"
    assert manifest["policy"] == "adaptive-v3"
    assert "wan2.2" in manifest["models"]
    assert "qwen" in manifest["models"]


# ------------------------------------------------------------ registry
def test_version_registry_tracks_components(tmp_path):
    registry = VersionRegistry(tmp_path / "vr.json")
    registry.set_component("director", "council-v1")
    registry.set_component("policy", "adaptive-v3")
    assert registry.get_component("director")["version"] == "council-v1"
    assert "director" in registry.components()
    assert "policy" in registry.components()


# ------------------------------------------------------------ audit
def test_audit_log_is_append_only(tmp_path):
    audit = AuditLog(tmp_path / "al.json")
    audit.record("release_create", {"release_id": "R1"})
    audit.record("release_approve", {"release_id": "R1"})
    entries = audit.entries()
    assert len(entries) == 2
    assert entries[0]["action"] == "release_create"
    assert entries[1]["action"] == "release_approve"
    assert audit.filter("release_approve")[0]["action"] == "release_approve"


# ------------------------------------------------------------ signer
def test_artifact_signer_roundtrip():
    signer = ArtifactSigner(Path("."))
    manifest = {"project": "p", "artifacts": {"a": "b"}}
    signed = signer.sign_manifest(manifest, "REL-1")
    assert signer.verify(signed, "REL-1") is True
    # tamper detection
    tampered = dict(signed)
    tampered["artifacts"] = {"a": "evil"}
    assert signer.verify(tampered, "REL-1") is False


def test_content_hash_is_deterministic():
    assert content_hash({"a": 1, "b": [1, 2]}) == content_hash({"b": [1, 2], "a": 1})
    assert content_hash({"a": 1}) != content_hash({"a": 2})


# ------------------------------------------------------------ release flow
def test_release_create_approve_rollback_certify(tmp_path):
    manager = _manager(tmp_path)
    manifest = manager.build_manifest()
    created = manager.create_release("REL-001", manifest, {"note": "first"})
    assert created["release_id"] == "REL-001"
    assert "audit" in created
    approved = manager.approve_release("REL-001")
    assert approved["approved"] is True
    rolled = manager.rollback_release("REL-001", reason="defect")
    assert rolled["rolled_back"] is True
    certified = manager.certification({"rollback": True, "audit": True, "artifact_hash": True})
    assert certified["passed"] is True
    actions = [e["action"] for e in manager.audit.entries()]
    assert actions == ["release_create", "release_approve", "release_rollback", "release_certify"]


def test_certification_fails_on_missing_gate(tmp_path):
    manager = _manager(tmp_path)
    result = manager.certification({"rollback": True, "audit": False, "artifact_hash": True})
    assert result["passed"] is False


# ------------------------------------------------------------ freeze
def test_production_freeze_creates_reproducible_package(tmp_path):
    pf = ProductionFreeze(release_root=tmp_path / "production_release")
    result = pf.freeze(
        "REL-FREEZE-001",
        director_decisions=[{"shot_id": "s1", "director": "llm-gpt"}],
        council_votes=[{"shot_id": "s1", "winner": "llm-gpt"}],
        policy_history=[{"version": "adaptive-v3"}],
        asset_registry=[{"asset": "c1.png"}],
        model_registry=[{"model": "wan2.2"}],
    )
    root = Path(result["root"])
    for sub in ("director_decisions", "council_votes", "policy_history",
                "asset_registry", "model_registry"):
        assert (root / sub).is_dir()
    assert (root / "manifest.json").exists()
    assert (root / "audit_report.md").exists()
    assert "生产冻结审计报告" in (root / "audit_report.md").read_text(encoding="utf-8")
    assert len(result["manifest"]["artifacts"]) >= 5


def test_production_freeze_verify_passes(tmp_path):
    pf = ProductionFreeze(release_root=tmp_path / "production_release")
    pf.freeze("REL-FREEZE-002", director_decisions=[{"shot_id": "s1"}])
    verify = pf.verify_package(tmp_path / "production_release" / "manifest.json")
    assert verify["manifest_valid"] is True
    assert verify["all_pass"] is True
