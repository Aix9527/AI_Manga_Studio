# -*- coding: utf-8 -*-
"""Wave 4E.2 Gate D: real ComfyUI submit/persist/kill/resume worker."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.provider_submission import (
    SubmissionOutcome,
    submit_or_resume,
)

COMFY_URL = "http://127.0.0.1:8188"
INPUT_IMAGE = "wan_test_input.png"
OUTPUT_PREFIX = "live_gateD_wan21"

# Minimal Wan 2.1 I2V workflow (validated by Gate B)
WORKFLOW = {
    "1": {"inputs": {"image": INPUT_IMAGE}, "class_type": "LoadImage"},
    "2": {"inputs": {
        "clip_name": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"},
        "class_type": "CLIPVisionLoader"},
    "3": {"inputs": {
        "clip_vision": ["2", 0], "image_1": ["1", 0],
        "strength_1": 1.0, "strength_2": 1.0, "crop": "center",
        "combine_embeds": "average", "force_offload": True},
        "class_type": "WanVideoClipVisionEncode"},
    "4": {"inputs": {
        "positive_prompt": "a cat walking gracefully, smooth motion",
        "negative_prompt": "bad quality, blurry, distorted",
        "t5": ["12", 0]},
        "class_type": "WanVideoTextEncode"},
    "5": {"inputs": {
        "width": 448, "height": 256, "num_frames": 13,
        "noise_aug_strength": 0.0, "start_latent_strength": 1.0,
        "end_latent_strength": 1.0, "force_offload": True,
        "vae": ["10", 0],
        "clip_embeds": ["3", 0], "start_image": ["1", 0]},
        "class_type": "WanVideoImageToVideoEncode"},
    "6": {"inputs": {
        "scheduler": "unipc", "steps": 6, "shift": 5.0,
        "start_step": 0, "end_step": -1},
        "class_type": "WanVideoSchedulerv2"},
    "7": {"inputs": {
        "model": ["8", 0], "image_embeds": ["5", 0],
        "cfg": 6.0, "seed": 42, "force_offload": True,
        "scheduler": ["6", 0], "text_embeds": ["4", 0]},
        "class_type": "WanVideoSamplerv2"},
    "8": {"inputs": {
        "model": "Wan2_1-I2V-14B-480P_fp8_e4m3fn.safetensors",
        "base_precision": "bf16",
        "quantization": "fp8_e4m3fn",
        "load_device": "main_device"},
        "class_type": "WanVideoModelLoader"},
    "9": {"inputs": {
        "samples": ["7", 0], "vae": ["10", 0],
        "enable_vae_tiling": True,
        "tile_x": 272, "tile_y": 272,
        "tile_stride_x": 144, "tile_stride_y": 128},
        "class_type": "WanVideoDecode"},
    "10": {"inputs": {
        "model_name": "wan_2.1_vae.safetensors",
        "precision": "fp16"},
        "class_type": "WanVideoVAELoader"},
    "11": {"inputs": {
        "filename_prefix": OUTPUT_PREFIX, "images": ["9", 0]},
        "class_type": "SaveImage"},
    "12": {"inputs": {
        "model_name": "umt5_xxl_fp16.safetensors",
        "precision": "bf16"},
        "class_type": "LoadWanVideoT5TextEncoder"},
}


class RealComfySubmitter:
    """POST /prompt to real ComfyUI, returning the real prompt_id."""

    def __init__(self, audit_file: Path):
        self.audit_file = Path(audit_file)

    def submit(self) -> str:
        import httpx

        resp = httpx.post(
            f"{COMFY_URL}/prompt", json={"prompt": WORKFLOW}, timeout=30
        )
        if resp.status_code != 200:
            raise RuntimeError(f"ComfyUI submit failed: {resp.status_code} {resp.text[:300]}")
        prompt_id = resp.json()["prompt_id"]
        with open(self.audit_file, "a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {"event": "POST_PROMPT", "pid": os.getpid(),
                     "prompt_id": prompt_id},
                    ensure_ascii=False,
                )
                + "\n"
            )
        return prompt_id


def poll_history(prompt_id: str, timeout: int = 1200) -> dict:
    import httpx

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = httpx.get(f"{COMFY_URL}/history/{prompt_id}", timeout=15)
        data = resp.json()
        entry = data.get(prompt_id, {})
        status = entry.get("status", {})
        if status.get("completed"):
            return entry
        if status.get("status_str") == "error":
            raise AssertionError(f"ComfyUI error: {entry.get('status')}")
        time.sleep(5)
    raise TimeoutError(f"poll_history timeout for {prompt_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--step-id", required=True)
    parser.add_argument("--attempt", type=int, default=0)
    parser.add_argument("--provider", default="wan2.1")
    parser.add_argument("--mode", required=True,
                        choices=["submit-a", "resume-b", "uncertain-b"])
    parser.add_argument("--audit-file", required=True)
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--ready-file", required=True)
    args = parser.parse_args()

    repository = JobRepository(OrchestrationDatabase(Path(args.database)))
    submitter = RealComfySubmitter(Path(args.audit_file))

    result = {
        "pid": os.getpid(),
        "mode": args.mode,
        "outcome": None,
        "submission_key": None,
        "remote_submission_id": None,
        "created": None,
        "error": None,
    }

    try:
        if args.mode == "submit-a":
            decision = submit_or_resume(
                repository, args.job_id, args.step_id, args.attempt,
                args.provider, submitter,
            )
            result["outcome"] = decision.outcome.value
            result["submission_key"] = decision.submission["submission_key"]
            result["remote_submission_id"] = decision.remote_submission_id
            result["created"] = True
        elif args.mode == "resume-b":
            # Worker B must NOT call the submitter. Use a guard submitter.
            class _Guard:
                def submit(self):
                    raise AssertionError("router must not be called during replay")

            decision = submit_or_resume(
                repository, args.job_id, args.step_id, args.attempt,
                args.provider, _Guard(),
            )
            result["outcome"] = decision.outcome.value
            result["submission_key"] = decision.submission["submission_key"]
            result["remote_submission_id"] = decision.remote_submission_id
            result["created"] = False
        elif args.mode == "uncertain-b":
            decision = submit_or_resume(
                repository, args.job_id, args.step_id, args.attempt,
                args.provider, submitter,
            )
            result["outcome"] = decision.outcome.value
            result["submission_key"] = decision.submission["submission_key"]
            result["remote_submission_id"] = decision.remote_submission_id
            result["created"] = False
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"

    Path(args.result_file).write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    Path(args.ready_file).write_text("READY", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
