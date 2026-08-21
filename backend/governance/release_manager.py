"""Release Manager (Phase 12.9-A, GPT spec).

Coordinates a frozen production release:

- collects current component versions (pipeline / director / policy / model)
- records them in the VersionRegistry
- writes the signed release manifest
- appends audit entries for create / approve / rollback

``build_manifest()`` returns the exact GPT Phase 12.9 signature shape::

    {project, pipeline, director, policy, models}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.governance.artifact_signer import ArtifactSigner, content_hash
from backend.governance.audit_log import AuditLog
from backend.governance.version_registry import VersionRegistry


class ReleaseManager:
    """Frozen release orchestration + governance gates."""

    def __init__(
        self,
        registry: VersionRegistry | None = None,
        audit: AuditLog | None = None,
        signer: ArtifactSigner | None = None,
    ):
        self.registry = registry or VersionRegistry()
        self.audit = audit or AuditLog()
        self.signer = signer or ArtifactSigner()

    # ------------------------------------------------------------ manifest
    def build_manifest(
        self,
        project: str = "归墟觉醒·天倾",
        pipeline: str = "v12.9",
        director: str = "council-v1",
        policy: str = "adaptive-v3",
        models: list[str] | None = None,
    ) -> dict:
        return {
            "project": project,
            "pipeline": pipeline,
            "director": director,
            "policy": policy,
            "models": models or ["wan2.2", "qwen"],
        }

    def register_versions(self, manifest: dict) -> None:
        """Persist each component version into the registry."""
        for name, version in manifest.items():
            if name == "project":
                continue
            if isinstance(version, list):
                for model in version:
                    self.registry.set_component(model, "current", {"source": "manifest"})
            else:
                self.registry.set_component(name, str(version), {"source": "manifest"})

    # ------------------------------------------------------------ release
    def create_release(
        self,
        release_id: str,
        manifest: dict,
        meta: dict | None = None,
    ) -> dict:
        """Create a signed release + audit trail."""
        self.register_versions(manifest)
        signed = self.signer.sign_manifest(manifest, release_id)
        components = {
            k: (v if isinstance(v, str) else ",".join(v) if isinstance(v, list) else str(v))
            for k, v in manifest.items() if k != "project"
        }
        self.registry.create_release(release_id, components, meta=meta)
        entry = self.audit.record("release_create", {
            "release_id": release_id,
            "manifest": signed,
            "meta": meta or {},
        })
        return {"release_id": release_id, "manifest": signed, "audit": entry}

    def approve_release(self, release_id: str, approved_by: str = "human") -> dict:
        entry = self.audit.record("release_approve", {
            "release_id": release_id,
            "approved_by": approved_by,
        })
        return {"release_id": release_id, "approved": True, "audit": entry}

    def rollback_release(self, release_id: str, reason: str = "defect", rolled_back_by: str = "human") -> dict:
        entry = self.audit.record("release_rollback", {
            "release_id": release_id,
            "reason": reason,
            "rolled_back_by": rolled_back_by,
        })
        return {"release_id": release_id, "rolled_back": True, "audit": entry}

    # ------------------------------------------------------------ gates
    def certification(self, checks: dict[str, bool]) -> dict:
        """12.9-C release certification gate summary."""
        passed = all(checks.values())
        entry = self.audit.record("release_certify", {
            "checks": checks,
            "passed": passed,
        })
        return {"passed": passed, "checks": checks, "audit": entry}
