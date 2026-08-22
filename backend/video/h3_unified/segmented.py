from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Sequence


CONTINUITY_MODES = ("auto", "latent", "frame_reference", "none")


@dataclass(frozen=True)
class H3SegmentPolicy:
    """Provider-neutral policy for H3 long-form segmented generation.

    Defaults are intentionally conservative for a 16 GB desktop GPU: one
    sampling pass, 5-15 second clips, post-generation 1.5x super resolution,
    and latent continuity only when the required Motion Context nodes exist.
    """

    segment_seconds: float = 10.0
    min_segment_seconds: float = 5.0
    max_segment_seconds: float = 15.0
    continuity: str = "auto"
    dual_sample: bool = False
    super_resolution_scale: float = 1.5
    gpu_vram_gb: float = 16.0
    video_context_frames: int = 22
    audio_context_frames: int = 24

    def __post_init__(self) -> None:
        if not 5 <= float(self.min_segment_seconds) <= 15:
            raise ValueError("H3 minimum segment duration must be between 5 and 15 seconds")
        if not self.min_segment_seconds <= float(self.segment_seconds) <= float(self.max_segment_seconds) <= 15:
            raise ValueError("H3 segment duration must stay within the 5-15 second production window")
        if self.continuity not in CONTINUITY_MODES:
            raise ValueError(f"unsupported H3 continuity mode: {self.continuity}")
        if self.super_resolution_scale < 1.0:
            raise ValueError("super_resolution_scale must be >= 1.0")


@dataclass(frozen=True)
class H3Segment:
    index: int
    duration_seconds: float
    prompt: str
    continuity: str
    load_previous_latent: bool
    latent_input: str = ""
    latent_output: str = ""
    trim_context_frames: int = 0
    audio_context_frames: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "duration_seconds": self.duration_seconds,
            "prompt": self.prompt,
            "continuity": self.continuity,
            "load_previous_latent": self.load_previous_latent,
            "latent_input": self.latent_input,
            "latent_output": self.latent_output,
            "trim_context_frames": self.trim_context_frames,
            "audio_context_frames": self.audio_context_frames,
        }


@dataclass(frozen=True)
class H3SegmentPlan:
    segments: tuple[H3Segment, ...]
    continuity: str
    dual_sample: bool
    super_resolution_scale: float
    gpu_profile: str

    @property
    def total_duration_seconds(self) -> float:
        return round(sum(item.duration_seconds for item in self.segments), 3)

    def to_dict(self) -> dict[str, object]:
        return {
            "continuity": self.continuity,
            "dual_sample": self.dual_sample,
            "super_resolution_scale": self.super_resolution_scale,
            "gpu_profile": self.gpu_profile,
            "total_duration_seconds": self.total_duration_seconds,
            "segments": [item.to_dict() for item in self.segments],
        }


def _gpu_profile(vram_gb: float) -> str:
    return "balanced_offload_16gb" if vram_gb <= 16 else "balanced_offload"


def _resolve_continuity(requested: str, motion_context_available: bool) -> str:
    if requested == "none":
        return "none"
    if requested == "frame_reference":
        return "frame_reference"
    if requested in ("auto", "latent") and motion_context_available:
        return "latent"
    return "frame_reference"


def _segment_durations(total: float, policy: H3SegmentPolicy) -> list[float]:
    if total < policy.min_segment_seconds:
        raise ValueError(f"segmented H3 generation requires at least {policy.min_segment_seconds:g} seconds")
    if total <= policy.max_segment_seconds:
        return [round(total, 3)]

    target = float(policy.segment_seconds)
    durations: list[float] = []
    remaining = float(total)
    while remaining > target:
        durations.append(target)
        remaining -= target
    if remaining > 0:
        durations.append(remaining)

    if len(durations) > 1 and durations[-1] < policy.min_segment_seconds:
        deficit = policy.min_segment_seconds - durations[-1]
        donor = durations[-2] - deficit
        if donor < policy.min_segment_seconds:
            raise ValueError("unable to rebalance H3 segments inside the 5-15 second window")
        durations[-2] = donor
        durations[-1] = policy.min_segment_seconds

    if any(not policy.min_segment_seconds <= item <= policy.max_segment_seconds for item in durations):
        raise ValueError("H3 segment planner produced a duration outside the 5-15 second window")
    return [round(item, 3) for item in durations]


def build_segment_plan(
    *,
    total_duration_seconds: float,
    global_prompt: str,
    policy: H3SegmentPolicy | None = None,
    segment_prompts: Sequence[str] = (),
    motion_context_available: bool = False,
    run_name: str = "h3_segmented",
) -> H3SegmentPlan:
    policy = policy or H3SegmentPolicy()
    if not str(global_prompt or "").strip() and not any(str(item or "").strip() for item in segment_prompts):
        raise ValueError("H3 segmented generation requires a prompt")

    durations = _segment_durations(float(total_duration_seconds), policy)
    continuity = _resolve_continuity(policy.continuity, motion_context_available)
    safe_run_name = str(PurePosixPath(str(run_name or "h3_segmented").replace("\\", "/"))).strip("/") or "h3_segmented"

    segments: list[H3Segment] = []
    previous_latent = ""
    for offset, duration in enumerate(durations):
        index = offset + 1
        prompt = (
            str(segment_prompts[offset]).strip()
            if offset < len(segment_prompts) and str(segment_prompts[offset]).strip()
            else str(global_prompt).strip()
        )
        latent_output = f"outputs/minimax_h3/{safe_run_name}/latent_context/clip_{index:05d}.safetensors"
        use_latent = continuity == "latent" and index > 1
        segments.append(
            H3Segment(
                index=index,
                duration_seconds=duration,
                prompt=prompt,
                continuity=continuity,
                load_previous_latent=use_latent,
                latent_input=previous_latent if use_latent else "",
                latent_output=latent_output if continuity == "latent" else "",
                trim_context_frames=policy.video_context_frames if use_latent else 0,
                audio_context_frames=policy.audio_context_frames if use_latent else 0,
            )
        )
        previous_latent = latent_output

    return H3SegmentPlan(
        segments=tuple(segments),
        continuity=continuity,
        dual_sample=bool(policy.dual_sample),
        super_resolution_scale=float(policy.super_resolution_scale),
        gpu_profile=_gpu_profile(float(policy.gpu_vram_gb)),
    )
