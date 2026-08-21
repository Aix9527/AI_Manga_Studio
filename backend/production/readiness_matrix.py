"""Production Readiness Matrix (Phase 13.4-B, GPT spec).

Aggregates seven production gates into a unified admission matrix:

- asset_ready:      Episode assets (Character Bible / World / Shot DNA) — reuses ReadinessGate v1
- identity_ready:   character identity assets: locked versions + identity + reference views
- prompt_ready:     every Prompt kind has an approved & locked version with resolvable variables
- workflow_ready:   workflow files exist, node bindings usable
- model_ready:      model files exist, not in the corrupt blacklist (deep SHA256 opt-in)
- gpu_ready:        disk space + ComfyUI health + task lease (WARNING instead of hard block)
- production_ready: aggregate

Every gate returns the same shape (GPT spec):

    {status: READY | BLOCKED | WARNING, required, checks, missing,
     recommended_actions, evidence, checked_at}
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from backend.characters.bible_v2.service import CharacterBibleService
from backend.production.model_guard import CORRUPT_MODEL_NAMES, EXPECTED_MODELS, verify_model_file
from backend.production.readiness import AssetReadinessGate
from backend.production.workflow_registry import (
    WAN22_I2V,
    WAN22_TI2V5B_NATIVE,
    select_wan_video_workflow,
)
from backend.prompt_intelligence.service import PromptIntelligenceService
from backend.shot_dna.library import ShotDNALibrary
from backend.world.service import WorldService

PROMPT_KINDS_REQUIRED = ["character", "world", "shot"]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _gate(status: str, *, required: bool, checks: int, missing: list[str], actions: list[str], evidence: list[str]) -> dict:
    return {
        "status": status,
        "required": required,
        "checks": checks,
        "missing": missing,
        "recommended_actions": actions,
        "evidence": evidence,
        "checked_at": _now(),
    }


class ProductionReadinessMatrix:
    """Unified production admission matrix (consumes frozen v1 gates)."""

    def __init__(
        self,
        *,
        asset_gate: AssetReadinessGate | None = None,
        characters: CharacterBibleService | None = None,
        world: WorldService | None = None,
        shot_dna: ShotDNALibrary | None = None,
        intelligence: PromptIntelligenceService | None = None,
        workflow_root: str | Path = "backend/production/workflows",
        model_root: str | Path = "storage/models",
        storage_root: str | Path = "storage",
        disk_min_gb: float = 5.0,
        comfy_health: Callable[[], bool] | None = None,
        vram_ok: bool | None = None,
        lease_ok: bool | None = None,
        deep_model_verify: bool = False,
    ):
        self.asset_gate = asset_gate or AssetReadinessGate(
            characters or CharacterBibleService(),
            world or WorldService(),
            shot_dna or ShotDNALibrary(),
        )
        self.characters = characters or CharacterBibleService()
        self.world = world or WorldService()
        self.shot_dna = shot_dna or ShotDNALibrary()
        self.intelligence = intelligence or PromptIntelligenceService()
        self.workflow_root = Path(workflow_root)
        self.model_root = Path(model_root)
        self.storage_root = Path(storage_root)
        self.disk_min_gb = disk_min_gb
        self.comfy_health = comfy_health
        self.vram_ok = vram_ok
        self.lease_ok = lease_ok
        self.deep_model_verify = deep_model_verify

    def check_project(self, project_id: str) -> dict:
        gates = {
            "asset_ready": self._asset_gate(project_id),
            "identity_ready": self._identity_gate(project_id),
            "prompt_ready": self._prompt_gate(),
            "workflow_ready": self._workflow_gate(),
            "model_ready": self._model_gate(),
            "gpu_ready": self._gpu_gate(),
        }
        gates["production_ready"] = self._aggregate(gates)
        return {"project_id": project_id, "gates": gates, **gates["production_ready"]}

    # ------------------------------------------------------------- gates
    def _asset_gate(self, project_id: str) -> dict:
        report = self.asset_gate.check_project(project_id)
        if report["ready"]:
            return _gate("READY", required=True, checks=3, missing=[], actions=[], evidence=["ReadinessGate v1 passed"])
        return _gate(
            "BLOCKED", required=True, checks=3, missing=report["missing"],
            actions=[f"补齐缺失资产: {', '.join(report['missing'])}"],
            evidence=["ReadinessGate v1 blocked"],
        )

    def _identity_gate(self, project_id: str) -> dict:
        bibles = self.characters.list()
        missing: list[str] = []
        evidence: list[str] = []
        for bible in bibles:
            locked = any(v.locked for v in bible.versions.values())
            reference = "front" in bible.views
            identity = bool(bible.identity.appearance or bible.identity.background)
            if not locked:
                missing.append(f"{bible.character_id}:no_locked_version")
            if not reference:
                missing.append(f"{bible.character_id}:no_front_reference")
            if not identity:
                missing.append(f"{bible.character_id}:no_identity")
            evidence.append(f"{bible.character_id}:locked={locked},reference={reference}")
        if not bibles:
            return _gate("BLOCKED", required=True, checks=3, missing=["no_character_bibles"],
                         actions=["创建 Character Bible（identity + 三视图 + 锁定版本）"], evidence=[])
        if missing:
            return _gate("BLOCKED", required=True, checks=3, missing=missing,
                         actions=["为角色补齐：锁定版本 / 正面参考图 / identity 指纹"], evidence=evidence)
        return _gate("READY", required=True, checks=3, missing=[], actions=[], evidence=evidence)

    def _prompt_gate(self) -> dict:
        templates = self.intelligence.list_templates()
        by_kind = {row["kind"]: row for row in templates}
        missing: list[str] = []
        evidence: list[str] = []
        for kind in PROMPT_KINDS_REQUIRED:
            row = by_kind.get(kind)
            active = ""
            variables_ok = False
            if row:
                for version in row.get("versions", []):
                    if version.get("status") == "locked":
                        active = version["version_id"]
                        base = version.get("base_template", "")
                        variables_ok = bool(base)
                        break
            if not active:
                missing.append(f"prompt_{kind}:no_locked_version")
            elif not variables_ok:
                missing.append(f"prompt_{kind}:variables_unresolvable")
            else:
                evidence.append(f"{kind}@{active}")
        if missing:
            return _gate("BLOCKED", required=True, checks=len(PROMPT_KINDS_REQUIRED), missing=missing,
                         actions=["将 character/world/shot 模板审批并锁定（Prompt Studio）"], evidence=evidence)
        return _gate("READY", required=True, checks=len(PROMPT_KINDS_REQUIRED), missing=[], actions=[], evidence=evidence)

    def _workflow_gate(self) -> dict:
        primary = WAN22_TI2V5B_NATIVE
        fallback = WAN22_I2V
        primary_path = self.workflow_root / primary.path.name
        fallback_path = self.workflow_root / fallback.path.name
        checks = 0
        missing: list[str] = []
        evidence: list[str] = []
        primary_ok = False
        fallback_ok = False
        for spec, path in ((primary, primary_path), (fallback, fallback_path)):
            exists = path.is_file()
            nodes = _load_workflow_nodes(path) if exists else []
            checks += 1
            evidence.append(f"{spec.name}=exists:{exists},nodes:{len(nodes)}")
            if exists and nodes:
                if spec.name == primary.name:
                    primary_ok = True
                else:
                    fallback_ok = True
            else:
                missing.append(spec.name if not exists else f"{spec.name}:no_nodes")
        if primary_ok:
            return _gate("READY", required=True, checks=checks, missing=[], actions=[], evidence=evidence)
        if primary_path.is_file() and (primary_path.name + ":no_nodes") in missing:
            return _gate("BLOCKED", required=True, checks=checks, missing=missing,
                         actions=["修复 native 工作流 JSON 的节点结构"], evidence=evidence)
        if fallback_ok:
            return _gate("WARNING", required=True, checks=checks, missing=["wan22_ti2v5b_native"],
                         actions=["恢复 native 工作流或接受 wrapper 回退链"], evidence=evidence)
        return _gate("BLOCKED", required=True, checks=checks, missing=missing,
                     actions=["恢复缺失的工作流 JSON"], evidence=evidence)

    def _model_gate(self) -> dict:
        missing: list[str] = []
        evidence: list[str] = []
        for name in EXPECTED_MODELS:
            path = self.model_root / name
            exists = path.is_file()
            evidence.append(f"{name}={exists}")
            if not exists:
                missing.append(f"{name}:missing")
                continue
            if name in CORRUPT_MODEL_NAMES:
                missing.append(f"{name}:corrupt_blacklist")
                continue
            if self.deep_model_verify:
                try:
                    verify_model_file(path)
                    evidence.append(f"{name}:sha256_ok")
                except (RuntimeError, FileNotFoundError) as exc:
                    missing.append(f"{name}:{type(exc).__name__}")
        if missing:
            return _gate("BLOCKED", required=True, checks=len(EXPECTED_MODELS), missing=missing,
                         actions=["下载/恢复模型文件；损坏模型（QR 码故障模式）禁止使用"], evidence=evidence)
        return _gate("READY", required=True, checks=len(EXPECTED_MODELS), missing=[], actions=[], evidence=evidence)

    def _gpu_gate(self) -> dict:
        evidence: list[str] = []
        missing: list[str] = []
        try:
            usage = shutil.disk_usage(self.storage_root)
            free_gb = round(usage.free / (1024 ** 3), 2)
            evidence.append(f"disk_free_gb={free_gb}")
        except OSError as exc:
            free_gb = 0.0
            evidence.append(f"disk_check_error={exc}")
        status = "READY"
        if free_gb < self.disk_min_gb:
            missing.append(f"disk_free_gb={free_gb}<{self.disk_min_gb}")
            status = "BLOCKED"
        if self.comfy_health is None:
            evidence.append("comfy_health=unchecked")
            if status == "READY":
                status = "WARNING"
        elif self.comfy_health():
            evidence.append("comfy_health=ok")
        else:
            missing.append("comfy_health=down")
            status = "BLOCKED"
        if self.vram_ok is None:
            evidence.append("vram=unverified")
            if status == "READY":
                status = "WARNING"
        elif self.vram_ok:
            evidence.append("vram=ok")
        else:
            missing.append("vram=insufficient")
            status = "BLOCKED"
        if self.lease_ok is None:
            evidence.append("task_lease=unverified")
            if status == "READY":
                status = "WARNING"
        elif self.lease_ok:
            evidence.append("task_lease=ok")
        else:
            missing.append("task_lease=unavailable")
            status = "BLOCKED"
        actions = {
            "BLOCKED": ["释放磁盘空间 / 恢复 ComfyUI 健康 / 核对显存余量与任务租约"],
            "WARNING": ["配置 ComfyUI 健康检查、显存探测与任务租约，移除 WARNING"],
        }.get(status, [])
        return _gate(status, required=True, checks=3, missing=missing, actions=actions, evidence=evidence)

    # ------------------------------------------------------------- aggregate
    @staticmethod
    def _aggregate(gates: dict[str, dict]) -> dict:
        blocked = [name for name, gate in gates.items() if gate["status"] == "BLOCKED"]
        warned = [name for name, gate in gates.items() if gate["status"] == "WARNING"]
        checks = sum(gate["checks"] for gate in gates.values())
        missing = [f"{name}:{item}" for name, gate in gates.items() for item in gate["missing"]]
        if blocked:
            status = "BLOCKED"
            action = f"阻断门禁: {', '.join(blocked)}"
        elif warned:
            status = "WARNING"
            action = f"告警门禁: {', '.join(warned)}"
        else:
            status = "READY"
            action = ""
        return _gate(
            status, required=True, checks=checks, missing=missing,
            actions=[action] if action else [],
            evidence=[f"{name}={gate['status']}" for name, gate in gates.items()],
        )


def _load_workflow_nodes(path: Path) -> list[dict]:
    """Extract node list from a ComfyUI workflow JSON (graph or API format)."""
    import json
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        nodes = data.get("nodes")
        if isinstance(nodes, list):
            return [n for n in nodes if isinstance(n, dict)]
        values = [v for v in data.values() if isinstance(v, dict) and "class_type" in v]
        return values
    return []