from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.video.h3_unified.live_gate import H3UnifiedLiveGate
from backend.video.h3_unified.reference_bundle import H3ReferenceBundle
from backend.video.h3_unified.ui_state import H3Mode, H3UnifiedRequest
from backend.video.providers.minimax_h3_unified_provider import MOTION_CONTEXT_NODES, UNIFIED_CONTROL_NODE


class FakeAdapter:
    async def get_object_info(self):
        return {UNIFIED_CONTROL_NODE: {}, **{name: {} for name in MOTION_CONTEXT_NODES}}


class MissingUnifiedAdapter:
    async def get_object_info(self):
        return {name: {} for name in MOTION_CONTEXT_NODES}


class FakeExecution:
    def __init__(self) -> None:
        self.calls = []

    async def execute(self, request, **kwargs):
        self.calls.append((request, kwargs))
        callback = kwargs.get("on_submitted")
        if callback:
            outcome = callback("prompt-live")
            if hasattr(outcome, "__await__"):
                await outcome
        return SimpleNamespace(
            prompt_id="prompt-live",
            runtime="external_unified",
            resumed=False,
            outputs={"1": {"videos": [{"filename": "smoke.mp4"}]}},
        )


def fake_command(args, **kwargs):
    assert args[0] == "nvidia-smi"
    return SimpleNamespace(
        returncode=0,
        stdout="NVIDIA GeForce RTX 5070 Ti, 16303, 590.00\n",
        stderr="",
    )


def fake_which(name: str):
    return f"C:/tools/{name}.exe"


@pytest.mark.asyncio
async def test_live_gate_preflight_reports_gpu_tools_comfy_and_unified_nodes() -> None:
    gate = H3UnifiedLiveGate(
        adapter=FakeAdapter(),
        execution=FakeExecution(),
        command_runner=fake_command,
        which=fake_which,
    )

    report = await gate.preflight()

    assert report["ok"] is True
    assert report["gpu"]["name"] == "NVIDIA GeForce RTX 5070 Ti"
    assert report["gpu"]["memory_total_mb"] == 16303
    assert report["tools"]["ffmpeg"]["available"] is True
    assert report["tools"]["ffprobe"]["available"] is True
    assert report["comfyui"]["reachable"] is True
    assert report["h3_unified"]["external_unified_available"] is True
    assert report["h3_unified"]["latent_continuity_available"] is True


@pytest.mark.asyncio
async def test_live_gate_fails_closed_when_unified_control_node_is_missing() -> None:
    gate = H3UnifiedLiveGate(
        adapter=MissingUnifiedAdapter(),
        execution=FakeExecution(),
        command_runner=fake_command,
        which=fake_which,
    )

    report = await gate.preflight()

    assert report["ok"] is False
    assert "h3_unified_node" in report["failures"]
    assert report["h3_unified"]["recommended_runtime"] == "unavailable"
    assert report["h3_unified"]["transparent_fallback_available"] is False
    assert report["h3_unified"]["alternate_route_requires_recompile"] is True


@pytest.mark.asyncio
async def test_live_gate_fails_closed_when_vram_is_below_smoke_profile() -> None:
    def low_vram(args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="NVIDIA GPU, 8192, 590.00\n", stderr="")

    gate = H3UnifiedLiveGate(
        adapter=FakeAdapter(),
        execution=FakeExecution(),
        command_runner=low_vram,
        which=fake_which,
    )

    report = await gate.preflight()

    assert report["ok"] is False
    assert "gpu_vram" in report["failures"]


@pytest.mark.asyncio
async def test_live_gate_default_run_never_submits_generation() -> None:
    execution = FakeExecution()
    gate = H3UnifiedLiveGate(
        adapter=FakeAdapter(),
        execution=execution,
        command_runner=fake_command,
        which=fake_which,
    )

    evidence = await gate.run(submit=False)

    assert evidence["preflight"]["ok"] is True
    assert evidence["submitted"] is False
    assert execution.calls == []


@pytest.mark.asyncio
async def test_live_gate_explicit_submit_checkpoints_prompt_and_writes_evidence(tmp_path: Path) -> None:
    execution = FakeExecution()
    gate = H3UnifiedLiveGate(
        adapter=FakeAdapter(),
        execution=execution,
        command_runner=fake_command,
        which=fake_which,
    )
    request = H3UnifiedRequest(
        mode=H3Mode.T2VA,
        prompt="cinematic rain corridor smoke test",
        references=H3ReferenceBundle(),
        duration_seconds=5,
        resolution="480p",
        aspect_ratio="9:16",
        steps=12,
        seed=42,
        gpu_vram_gb=16,
    )
    evidence_path = tmp_path / "h3-live.json"

    evidence = await gate.run(request=request, submit=True, evidence_path=evidence_path)

    assert evidence["submitted"] is True
    assert evidence["prompt_id"] == "prompt-live"
    assert evidence["runtime"] == "external_unified"
    assert evidence_path.is_file()
    text = evidence_path.read_text(encoding="utf-8")
    assert '"prompt_id": "prompt-live"' in text
    assert execution.calls[0][1]["subfolder"].startswith("h3_unified/live/")
