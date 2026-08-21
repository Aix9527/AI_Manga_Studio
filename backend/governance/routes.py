"""Production Governance API (Phase 12.9-A, GPT approved).

Endpoints:
- GET  /api/governance/registry            component + release versions
- GET  /api/governance/audit               append-only audit trail
- POST /api/governance/release             create a signed release
- POST /api/governance/release/approve     human approval
- POST /api/governance/release/rollback    rollback (audited)
- POST /api/governance/certify             release certification gates
- POST /api/governance/freeze              12.9-D production freeze package
- POST /api/governance/verify              verify package artifact hashes
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.governance import AuditLog, ReleaseManager, VersionRegistry
from backend.governance.production_freeze import ProductionFreeze

router = APIRouter(prefix="/api/governance", tags=["governance"])

GOV_ROOT = Path("storage/governance")


class ReleaseBody(BaseModel):
    release_id: str
    project: str = "归墟觉醒·天倾"
    pipeline: str = "v12.9"
    director: str = "council-v1"
    policy: str = "adaptive-v3"
    models: list[str] = ["wan2.2", "qwen"]
    meta: dict = {}


class ApproveBody(BaseModel):
    release_id: str
    approved_by: str = "human"


class RollbackBody(BaseModel):
    release_id: str
    reason: str = "defect"
    rolled_back_by: str = "human"


class CertifyBody(BaseModel):
    checks: dict[str, bool]


class FreezeBody(BaseModel):
    release_id: str
    project: str = "归墟觉醒·天倾"
    director_decisions: list[dict] = []
    council_votes: list[dict] = []
    policy_history: list[dict] = []
    asset_registry: list[dict] = []
    model_registry: list[dict] = []


def _manager() -> ReleaseManager:
    return ReleaseManager(
        VersionRegistry(GOV_ROOT / "version_registry.json"),
        AuditLog(GOV_ROOT / "audit_log.json"),
    )


@router.get("/registry")
def registry():
    return _manager().registry.summary()


@router.get("/audit")
def audit(action: Optional[str] = None):
    return {"entries": _manager().audit.filter(action)}


@router.post("/release")
def create_release(body: ReleaseBody):
    manager = _manager()
    manifest = manager.build_manifest(
        project=body.project, pipeline=body.pipeline,
        director=body.director, policy=body.policy, models=body.models,
    )
    return manager.create_release(body.release_id, manifest, meta=body.meta)


@router.post("/release/approve")
def approve_release(body: ApproveBody):
    return _manager().approve_release(body.release_id, approved_by=body.approved_by)


@router.post("/release/rollback")
def rollback_release(body: RollbackBody):
    return _manager().rollback_release(
        body.release_id, reason=body.reason, rolled_back_by=body.rolled_back_by
    )


@router.post("/certify")
def certify(body: CertifyBody):
    return _manager().certification(body.checks)


@router.post("/freeze")
def freeze(body: FreezeBody):
    pf = ProductionFreeze(release_root=Path("production_release"))
    return pf.freeze(
        body.release_id,
        project=body.project,
        director_decisions=body.director_decisions,
        council_votes=body.council_votes,
        policy_history=body.policy_history,
        asset_registry=body.asset_registry,
        model_registry=body.model_registry,
    )


@router.post("/verify")
def verify(body: dict):
    manifest_path = body.get("manifest_path")
    if not manifest_path:
        raise HTTPException(status_code=400, detail="manifest_path required")
    return ProductionFreeze(release_root=Path("production_release")).verify_package(manifest_path)
