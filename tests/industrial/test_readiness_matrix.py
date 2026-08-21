"""Phase 13.4-B: Production Readiness Matrix tests (seven-gate admission)."""

from __future__ import annotations

import json

import pytest

from backend.characters.bible_v2.service import CharacterBibleService
from backend.production.model_guard import EXPECTED_MODELS
from backend.production.readiness import AssetReadinessGate
from backend.production.readiness_matrix import ProductionReadinessMatrix
from backend.prompt_intelligence.service import PromptIntelligenceService
from backend.shot_dna.library import ShotDNALibrary
from backend.world.service import WorldService


def _complete_bible(service: CharacterBibleService, cid: str) -> None:
    service.create(cid, name=f"角色{cid}")
    service.update_identity(cid, background="归墟世界主角", appearance={"hair": "黑发", "eye": "黑瞳"})
    for key in ("front", "side", "back"):
        service.add_view(cid, key, prompt=f"{key} view")
    for key in ("neutral", "angry", "sad", "fear", "smile", "surprise"):
        service.add_expression(cid, key, prompt=f"{key} expr")
    for key in ("walk", "run", "fight", "sit", "interact", "emotional"):
        service.add_action(cid, key, description=key)


def _full_matrix(tmp_path) -> tuple[ProductionReadinessMatrix, dict]:
    bible = CharacterBibleService(str(tmp_path / "bible"))
    world = WorldService(str(tmp_path / "world"))
    dna = ShotDNALibrary(str(tmp_path / "dna.json"))
    pi = PromptIntelligenceService(str(tmp_path / "pi"))
    for kind, base in (("character", "portrait of {character_name}"), ("world", "world {world_name}"), ("shot", "{prompt_template}")):
        row = pi.create_template(name=f"{kind}_prompt", kind=kind, base_template=base)
        pi.set_version_status(row["id"], "v1", "approved", approved_by="导演")
        pi.set_version_status(row["id"], "v1", "locked")
    world.create_world("PROJ-1", name="归墟", era="未来科幻")
    world.note_environment("PROJ-1", kind="physics_rule", content="禁止时间回溯")

    workflow_root = tmp_path / "workflows"
    workflow_root.mkdir(parents=True, exist_ok=True)
    (workflow_root / "wan22_ti2v5b_native.json").write_text(
        json.dumps({"nodes": [{"class_type": "UNETLoader"}, {"class_type": "KSampler"}]}), encoding="utf-8"
    )
    (workflow_root / "wan22_i2v.json").write_text(json.dumps({"nodes": [{"class_type": "WanVideoSampler"}]}), encoding="utf-8")

    model_root = tmp_path / "models"
    model_root.mkdir(parents=True, exist_ok=True)
    for name in EXPECTED_MODELS:
        (model_root / name).write_bytes(b"fake model bytes")

    matrix = ProductionReadinessMatrix(
        asset_gate=AssetReadinessGate(bible, world, dna),
        characters=bible, world=world, shot_dna=dna, intelligence=pi,
        workflow_root=workflow_root, model_root=model_root,
        storage_root=tmp_path, disk_min_gb=0.001,
        comfy_health=lambda: True, vram_ok=True, lease_ok=True,
    )
    return matrix, {"bible": bible, "world": world, "pi": pi}


def test_empty_project_blocked(tmp_path):
    matrix = _full_matrix(tmp_path)[0]
    report = matrix.check_project("PROJ-EMPTY")
    assert report["status"] == "BLOCKED"
    assert "asset_ready" in report["missing"][0]
    assert report["gates"]["identity_ready"]["status"] == "BLOCKED"


def test_full_project_ready(tmp_path):
    matrix, deps = _full_matrix(tmp_path)
    _complete_bible(deps["bible"], "CH-001")
    deps["bible"].add_version("CH-001", "v1", approved=True)
    deps["bible"].set_version_status("CH-001", "v1", approved=True, locked=True)
    report = matrix.check_project("PROJ-1")
    assert report["status"] == "READY", report
    for name in ("asset_ready", "identity_ready", "prompt_ready", "workflow_ready", "model_ready", "production_ready"):
        assert report["gates"][name]["status"] == "READY", (name, report["gates"][name])


def test_gpu_warning_propagates(tmp_path):
    matrix, deps = _full_matrix(tmp_path)
    _complete_bible(deps["bible"], "CH-001")
    deps["bible"].add_version("CH-001", "v1", approved=True)
    deps["bible"].set_version_status("CH-001", "v1", approved=True, locked=True)
    matrix.comfy_health = None  # unverified -> WARNING
    report = matrix.check_project("PROJ-1")
    assert report["status"] == "WARNING"
    assert report["gates"]["gpu_ready"]["status"] == "WARNING"


def test_model_missing_blocks(tmp_path):
    matrix, deps = _full_matrix(tmp_path)
    for name in EXPECTED_MODELS:
        (tmp_path / "models" / name).unlink()
    report = matrix.check_project("PROJ-1")
    assert report["gates"]["model_ready"]["status"] == "BLOCKED"
    assert report["status"] == "BLOCKED"


def test_workflow_fallback_warns(tmp_path):
    matrix, deps = _full_matrix(tmp_path)
    (tmp_path / "workflows" / "wan22_ti2v5b_native.json").unlink()
    report = matrix.check_project("PROJ-1")
    assert report["gates"]["workflow_ready"]["status"] == "WARNING"