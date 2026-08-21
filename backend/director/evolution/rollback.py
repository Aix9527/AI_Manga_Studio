"""Policy version store + rollback (Phase 11.3-C, GPT design).

Every policy change is a versioned snapshot (``router_policy_v{n}.yaml``)
plus a traceable evolution log. Rollback restores the previous snapshot and
records before/after, affected shots and score delta.

Requirements from GPT:
- ``rollback_window: 200`` (keep at least that many versions)
- any policy change records: before, after, affected shots, score delta
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_yaml(path: Path) -> dict:
    if path.exists():
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {}


def _save_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    tmp.replace(path)


class PolicyVersionStore:
    """Snapshots policy YAML files and keeps a JSON evolution log."""

    def __init__(self, policy_path: str | Path, versions_dir: str | Path | None = None,
                 log_name: str = "evolution_log.json", rollback_window: int = 200,
                 prefix: str = "router_policy"):
        self.policy_path = Path(policy_path)
        self.versions_dir = Path(versions_dir) if versions_dir else self.policy_path.parent
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.versions_dir / log_name
        self.rollback_window = rollback_window
        self.prefix = prefix

    # ---------------------------------------------------------- versions
    def latest_version(self) -> int:
        numbers = [
            int(m.group(1))
            for m in (re.match(rf"{re.escape(self.prefix)}_v(\d+)\.yaml", p.name) for p in self.versions_dir.iterdir())
            if m
        ]
        return max(numbers) if numbers else 0

    def snapshot(self) -> int:
        """Persist the current policy file as ``router_policy_v{n}.yaml``."""
        version = self.latest_version() + 1
        data = _load_yaml(self.policy_path)
        data["snapshot_of_version"] = str(data.get("version", "?"))
        _save_yaml(self.versions_dir / f"{self.prefix}_v{version}.yaml", data)
        self._prune()
        return version

    def load_version(self, version: int) -> dict:
        return _load_yaml(self.versions_dir / f"{self.prefix}_v{version}.yaml")

    def restore(self, version: int) -> dict:
        """Restore the active policy file from a snapshot.

        The content is reverted but the revision field stays monotonic
        (like ``git revert``) so history is unambiguous.
        """
        data = self.load_version(version)
        if not data:
            raise FileNotFoundError(f"no snapshot router_policy_v{version}.yaml")
        current = _load_yaml(self.policy_path)
        current_version = current.get("version")
        if isinstance(current_version, (int, float)):
            data["version"] = round(float(current_version) + 0.1, 1)
        _save_yaml(self.policy_path, data)
        return data

    def _prune(self) -> None:
        versions = sorted(
            int(m.group(1)) for m in
            (re.match(rf"{re.escape(self.prefix)}_v(\d+)\.yaml", p.name) for p in self.versions_dir.iterdir())
            if m
        )
        for version in versions[:-self.rollback_window]:
            (self.versions_dir / f"{self.prefix}_v{version}.yaml").unlink(missing_ok=True)

    # -------------------------------------------------------------- log
    def log(self, action: str, entry: dict) -> dict:
        log_data = self._load_log()
        record = {
            "id": f"EVO-{uuid.uuid4().hex[:10]}",
            "action": action,
            "created_at": _now(),
            **entry,
        }
        log_data.append(record)
        tmp = self.log_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(log_data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.log_path)
        return record

    def entries(self) -> list[dict]:
        return self._load_log()

    def _load_log(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        try:
            data = json.loads(self.log_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []
