from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.video.providers.minimax_h3_unified_provider import H3UnifiedProvider

from .comfy_media import H3ComfyMediaAdapter
from .execution import H3UnifiedExecutionService
from .ui_state import H3UnifiedRequest


LIVE_GATE_SCHEMA = "ai-manga/h3-unified-live-gate-v1"
DEFAULT_MIN_VRAM_MB = 15_000


@dataclass
class H3UnifiedLiveGate:
    """Fail-closed local preflight and opt-in smoke submission for H3 Unified."""

    adapter: Any = field(default_factory=H3ComfyMediaAdapter)
    execution: Any | None = None
    command_runner: Callable[..., Any] = subprocess.run
    which: Callable[[str], str | None] = shutil.which
    min_vram_mb: int = DEFAULT_MIN_VRAM_MB

    def __post_init__(self) -> None:
        if self.execution is None:
            self.execution = H3UnifiedExecutionService(adapter=self.adapter)

    async def preflight(self) -> dict[str, Any]:
        failures: list[str] = []
        gpu = self._gpu_report()
        if not gpu.get("available"):
            failures.append("gpu")
        elif int(gpu.get("memory_total_mb", 0)) < int(self.min_vram_mb):
            failures.append("gpu_vram")

        tools = {
            "ffmpeg": self._tool_report("ffmpeg", "AI_MANGA_FFMPEG"),
            "ffprobe": self._tool_report("ffprobe", "AI_MANGA_FFPROBE"),
        }
        for name, report in tools.items():
            if not report["available"]:
                failures.append(name)

        comfy_report: dict[str, Any]
        h3_report: dict[str, Any]
        nodes_checked = False
        provider = H3UnifiedProvider()
        try:
            object_info = await self.adapter.get_object_info()
            comfy_report = {
                "reachable": True,
                "base_url": _adapter_base_url(self.adapter),
                "node_count": len(object_info) if isinstance(object_info, dict) else 0,
            }
            h3_report = provider.preflight(object_info)
            h3_report["check_status"] = "checked"
            nodes_checked = True
        except Exception as error:
            comfy_report = {
                "reachable": False,
                "base_url": _adapter_base_url(self.adapter),
                "error": str(error),
            }
            h3_report = {
                "provider": provider.provider_name,
                "check_status": "unavailable",
                "reason": "comfyui_unreachable",
                "external_unified_available": None,
                "latent_continuity_available": None,
                "recommended_runtime": "unavailable",
                "transparent_fallback_available": False,
                "alternate_route": provider.alternate_route,
                "alternate_route_requires_recompile": True,
                "missing_nodes": [],
                "missing_motion_context_nodes": [],
            }
            failures.append("comfyui")

        if nodes_checked:
            if not h3_report.get("external_unified_available"):
                failures.append("h3_unified_node")
            if not h3_report.get("latent_continuity_available"):
                failures.append("motion_context_nodes")

        return {
            "schema": LIVE_GATE_SCHEMA,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "ok": not failures,
            "failures": failures,
            "gpu": gpu,
            "tools": tools,
            "comfyui": comfy_report,
            "h3_unified": h3_report,
            "smoke_profile": {
                "min_vram_mb": int(self.min_vram_mb),
                "resolution": "480p",
                "duration_seconds": 5,
                "steps": 12,
            },
        }

    async def run(
        self,
        *,
        request: H3UnifiedRequest | None = None,
        submit: bool = False,
        evidence_path: str | Path | None = None,
        resume_prompt_id: str = "",
    ) -> dict[str, Any]:
        preflight = await self.preflight()
        evidence: dict[str, Any] = {
            "schema": LIVE_GATE_SCHEMA,
            "preflight": preflight,
            "submitted": False,
            "state": "preflight_only",
        }
        path = Path(evidence_path) if evidence_path else None
        if path is not None:
            _write_evidence(path, evidence)
        if not submit:
            return evidence
        if not preflight["ok"]:
            evidence["state"] = "blocked_by_preflight"
            if path is not None:
                _write_evidence(path, evidence)
            raise RuntimeError(
                "H3 unified live submission blocked by preflight: "
                + ", ".join(preflight["failures"])
            )
        if request is None:
            raise ValueError("H3 unified live submission requires a request")

        accepted_prompt = str(resume_prompt_id or "")

        def checkpoint(prompt_id: str) -> None:
            nonlocal accepted_prompt
            accepted_prompt = str(prompt_id)
            evidence.update(
                {
                    "submitted": True,
                    "state": "prompt_accepted",
                    "prompt_id": accepted_prompt,
                }
            )
            if path is not None:
                _write_evidence(path, evidence)

        subfolder = "h3_unified/live/" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        try:
            result = await self.execution.execute(
                request,
                subfolder=subfolder,
                on_submitted=None if resume_prompt_id else checkpoint,
                resume_prompt_id=resume_prompt_id,
            )
        except Exception as error:
            evidence.update(
                {
                    "submitted": bool(accepted_prompt),
                    "state": "accepted_but_incomplete" if accepted_prompt else "submit_failed",
                    "prompt_id": accepted_prompt,
                    "error": str(error),
                }
            )
            if path is not None:
                _write_evidence(path, evidence)
            raise

        evidence.update(
            {
                "submitted": True,
                "state": "completed",
                "prompt_id": str(result.prompt_id),
                "runtime": str(result.runtime),
                "resumed": bool(getattr(result, "resumed", False)),
                "outputs": result.outputs,
            }
        )
        if path is not None:
            _write_evidence(path, evidence)
        return evidence

    def _gpu_report(self) -> dict[str, Any]:
        try:
            completed = self.command_runner(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,driver_version",
                    "--format=csv,noheader,nounits",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except Exception as error:
            return {"available": False, "error": str(error)}
        if int(getattr(completed, "returncode", 1)) != 0:
            return {
                "available": False,
                "error": str(getattr(completed, "stderr", "") or "nvidia-smi failed").strip(),
            }
        first_line = str(getattr(completed, "stdout", "")).strip().splitlines()
        if not first_line:
            return {"available": False, "error": "nvidia-smi returned no GPU rows"}
        parts = [part.strip() for part in first_line[0].split(",")]
        if len(parts) < 3:
            return {"available": False, "error": "nvidia-smi returned malformed GPU data"}
        try:
            memory_total_mb = int(float(parts[1]))
        except ValueError:
            return {"available": False, "error": "nvidia-smi returned invalid VRAM data"}
        return {
            "available": True,
            "name": parts[0],
            "memory_total_mb": memory_total_mb,
            "driver_version": parts[2],
        }

    def _tool_report(self, command: str, env_name: str) -> dict[str, Any]:
        configured = str(os.environ.get(env_name, "") or "").strip()
        resolved = None
        if configured:
            configured_path = Path(configured)
            if configured_path.is_file():
                resolved = str(configured_path)
            else:
                resolved = self.which(configured)
        if not resolved:
            resolved = self.which(command)
        return {"available": bool(resolved), "path": str(resolved or "")}


def _adapter_base_url(adapter: Any) -> str:
    base = getattr(adapter, "base", adapter)
    return str(getattr(base, "base_url", "http://127.0.0.1:8188"))


def _write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json.tmp",
        prefix=f".{path.stem}.",
        dir=path.parent,
        delete=False,
    ) as file:
        json.dump(evidence, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
        temp_path = Path(file.name)
    temp_path.replace(path)
    if os.name != "nt":
        try:
            descriptor = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)
