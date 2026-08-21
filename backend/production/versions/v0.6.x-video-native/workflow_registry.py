from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkflowSpec:
    name: str
    path: Path
    supports_end_frame: bool = False


WORKFLOW_ROOT = Path("backend/production/workflows")

# WanVideoWrapper chain (rollback path). The wrapper's
# WanVideoEncode -> WanVideoEmptyEmbeds -> WanVideoSampler protocol.
WAN22_I2V = WorkflowSpec("wan22_i2v", WORKFLOW_ROOT / "wan22_i2v.json")
WAN22_FLF2V = WorkflowSpec(
    "wan22_flf2v",
    WORKFLOW_ROOT / "wan22_flf2v.json",
    supports_end_frame=True,
)

# Official ComfyUI-native Wan2.2 TI2V-5B chain (production default):
# UNETLoader -> ModelSamplingSD3(shift=8) -> Wan22ImageToVideoLatent ->
# KSampler(uni_pc/simple, steps=20, cfg=5, denoise=1) -> VAEDecode.
# Validated 2026-08-05 after replacing the corrupted model file.
WAN22_TI2V5B_NATIVE = WorkflowSpec(
    "wan22_ti2v5b_native",
    WORKFLOW_ROOT / "wan22_ti2v5b_native.json",
)

# "native" (default) or "wrapper" for the legacy rollback chain.
WAN22_WORKFLOW_MODE = os.environ.get("WAN22_WORKFLOW_MODE", "native").strip().lower()


def select_wan_video_workflow(*, has_end_frame: bool) -> WorkflowSpec:
    if WAN22_WORKFLOW_MODE == "wrapper":
        if has_end_frame and WAN22_FLF2V.path.exists():
            return WAN22_FLF2V
        return WAN22_I2V
    # Native mode: end-frame FLF2V is not supported by the 5B native chain yet.
    if WAN22_TI2V5B_NATIVE.path.exists():
        return WAN22_TI2V5B_NATIVE
    if has_end_frame and WAN22_FLF2V.path.exists():
        return WAN22_FLF2V
    return WAN22_I2V
