from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from backend.workspace.models import ProjectAsset
from backend.workspace.repository import WorkspaceRepository


class AssetRegistry:
    """Content-hash asset registry with dedup + recovery manifests (Jellyfish-inspired).

    Wraps ``WorkspaceRepository.add_project_asset`` with SHA-256 dedup: registering
    an identical (project, kind, hash) asset returns the previously stored one,
    which is what makes retried generation idempotent.
    """

    def __init__(self, repo: WorkspaceRepository):
        self.repo = repo

    @staticmethod
    def content_hash(path: str | Path, chunk_size: int = 1 << 20) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def register(
        self,
        job_id: str,
        kind: str,
        path: str | Path,
        *,
        stage_key: str = "",
        scene_id: str = "",
        shot_id: str = "",
        parent_artifact_id: int | None = None,
        quality_status: str = "unreviewed",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ProjectAsset, bool]:
        """Register an asset; returns (asset, created). created=False => dedup hit."""
        digest = self.content_hash(path)
        meta = dict(metadata or {})
        meta["content_hash"] = digest
        # project lookup via job (repo helper needs project_id: query through db is hidden,
        # so resolve via the returned row from repo by listing)
        existing = self._find_existing(job_id, kind, digest)
        if existing is not None:
            return existing, False
        asset = self.repo.add_project_asset(
            job_id,
            kind,
            str(path),
            stage_key=stage_key,
            scene_id=scene_id,
            shot_id=shot_id,
            parent_artifact_id=parent_artifact_id,
            quality_status=quality_status,
            metadata=meta,
            sha256=digest,
        )
        return asset, True

    def _find_existing(self, job_id: str, kind: str, digest: str) -> ProjectAsset | None:
        """Resolve project_id from the job row, then dedup by hash."""
        try:
            with self.repo.db.transaction() as conn:
                row = conn.execute("SELECT project_id FROM jobs WHERE id=?", (job_id,)).fetchone()
                if row is None:
                    return None
                hit = conn.execute(
                    """SELECT * FROM artifacts
                       WHERE project_id=? AND kind=? AND sha256=? AND active=1
                       ORDER BY id DESC LIMIT 1""",
                    (row["project_id"], kind, digest),
                ).fetchone()
            return self.repo._asset_from_row(hit) if hit else None
        except Exception:
            return None

    def recovery_manifest(self, project_id: str) -> dict:
        """Group active assets by stage — used to resume after a worker restart."""
        assets = self.repo.list_project_assets(project_id)
        by_stage: dict[str, list[dict]] = {}
        for a in assets:
            key = a.stage_key or "unsorted"
            by_stage.setdefault(key, []).append(
                {
                    "id": a.id,
                    "kind": a.kind,
                    "shot_id": a.shot_id,
                    "version": a.version,
                    "quality_status": a.quality_status,
                    "path": a.path,
                }
            )
        return {"project_id": project_id, "total_assets": len(assets), "by_stage": by_stage}
