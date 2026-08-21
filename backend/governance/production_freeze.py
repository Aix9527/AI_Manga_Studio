"""Production Freeze (Phase 12.9-D, GPT spec).

Creates the reproducible release package under ``production_release/``::

    production_release/
    ├── episode_01_master.mp4       (optional, copied when present)
    ├── manifest.json
    ├── director_decisions/
    ├── council_votes/
    ├── policy_history/
    ├── asset_registry/
    ├── model_registry/
    └── audit_report.md

Every file is content-hashed in the manifest so the package can be verified
later (12.9-C artifact hash gate).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.governance.artifact_signer import ArtifactSigner, file_hash
from backend.governance.audit_log import AuditLog
from backend.governance.release_manager import ReleaseManager


class ProductionFreeze:
    """Assemble + verify a reproducible production release package."""

    def __init__(
        self,
        release_root: str | Path = "production_release",
        release_manager: ReleaseManager | None = None,
        signer: ArtifactSigner | None = None,
    ):
        self.root = Path(release_root)
        self.manager = release_manager or ReleaseManager()
        self.signer = signer or ArtifactSigner(release_root)

    def _ensure_dirs(self) -> None:
        for name in ("director_decisions", "council_votes", "policy_history",
                     "asset_registry", "model_registry"):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def write_json(self, rel_path: str, data: Any) -> Path:
        target = self.root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def freeze(
        self,
        release_id: str,
        *,
        project: str = "归墟觉醒·天倾",
        manifest_extra: dict | None = None,
        director_decisions: list[dict] | None = None,
        council_votes: list[dict] | None = None,
        policy_history: list[dict] | None = None,
        asset_registry: list[dict] | None = None,
        model_registry: list[dict] | None = None,
        master_video: str | Path | None = None,
    ) -> dict:
        """Build the full release package; returns the signed manifest."""
        self._ensure_dirs()
        self.write_json("director_decisions/decisions.json", director_decisions or [])
        self.write_json("council_votes/votes.json", council_votes or [])
        self.write_json("policy_history/history.json", policy_history or [])
        self.write_json("asset_registry/assets.json", asset_registry or [])
        self.write_json("model_registry/models.json", model_registry or [])

        manifest = self.manager.build_manifest(project=project)
        if manifest_extra:
            manifest.update(manifest_extra)
        manifest["release_id"] = release_id

        artifacts = {
            "director_decisions/decisions.json": file_hash(self.root / "director_decisions/decisions.json"),
            "council_votes/votes.json": file_hash(self.root / "council_votes/votes.json"),
            "policy_history/history.json": file_hash(self.root / "policy_history/history.json"),
            "asset_registry/assets.json": file_hash(self.root / "asset_registry/assets.json"),
            "model_registry/models.json": file_hash(self.root / "model_registry/models.json"),
        }
        if master_video and Path(master_video).exists():
            video_rel = "episode_01_master.mp4"
            import shutil
            shutil.copy2(Path(master_video), self.root / video_rel)
            artifacts[video_rel] = file_hash(self.root / video_rel)

        manifest["artifacts"] = artifacts
        signed = self.signer.sign_manifest(manifest, release_id)
        manifest_path = self.write_json("manifest.json", signed)
        self.write_audit_report(signed, artifacts)

        audit = self.manager.audit.record("production_freeze", {
            "release_id": release_id,
            "manifest_path": str(manifest_path),
            "artifacts": artifacts,
        })
        return {"manifest": signed, "audit": audit, "root": str(self.root)}

    def write_audit_report(self, manifest: dict, artifacts: dict[str, str]) -> Path:
        """Write the GPT-specified audit_report.md into the freeze package."""
        lines = [
            "# 生产冻结审计报告",
            "",
            f"- release_id: `{manifest.get('release_id', '-')}`",
            f"- project: `{manifest.get('project', '-')}`",
            f"- pipeline: `{manifest.get('pipeline', '-')}`",
            f"- director: `{manifest.get('director', '-')}`",
            f"- policy: `{manifest.get('policy', '-')}`",
            f"- models: `{', '.join(manifest.get('models') or [])}`",
            f"- signature: `{manifest.get('signature', '-')}`",
            "",
            "## 产物哈希（sha256）",
            "",
        ]
        for rel, digest in artifacts.items():
            lines.append(f"- `{rel}` → `{digest}`")
        lines += [
            "",
            "## 结论",
            "",
            "本包由 ReleaseManager 构建、ArtifactSigner 签名，全部产物内容哈希已写入 manifest.json，可通过 `verify_package` 复验。",
            "",
        ]
        target = self.root / "audit_report.md"
        target.write_text("\n".join(lines), encoding="utf-8")
        return target

    def verify_package(self, manifest_path: str | Path) -> dict:
        """Re-verify every artifact hash + manifest signature."""
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        release_id = data.get("release_id", "")
        ok = self.signer.verify(data, release_id)
        results: dict[str, bool] = {}
        for rel, expected in (data.get("artifacts") or {}).items():
            actual = file_hash(self.root / rel)
            results[rel] = actual == expected
        return {
            "manifest_valid": ok,
            "artifacts": results,
            "all_pass": ok and all(results.values()),
        }
