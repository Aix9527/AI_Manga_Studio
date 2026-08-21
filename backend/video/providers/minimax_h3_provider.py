"""MiniMaxH3 Provider (Phase 15.3-A, GPT 冻结规格).

ComfyUI Native Provider：FL2V 首尾帧 → 15 秒以上长镜头视频。
- MiniMaxH3Director 自动导演（global_prompt + timeline_data）+ 首尾帧 refs
- 原生立体声（audio_vae）
- 统一接口：generate(start_frame, end_frame, prompt, duration, fps, metadata)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from backend.production.comfy_adapter import (
    ComfyUIAdapter,
    ProductionError,
    ProductionErrorCode,
)
from backend.production.providers import MediaArtifact
from backend.production.workflow_templates import WorkflowTemplate

WORKFLOW_NAME = "minimax_h3_fl2va_native.json"


SHOT_MAX_SECONDS = 15.0


def _build_shots(*, first_ref: str, last_ref: str, total_frames: int,
                 frame_rate: float, ref_max_size: int, width: int, height: int) -> list[dict]:
    """多段 timeline：每段 ≤15s，中间段首尾帧自动衔接（长视频 3-5 分钟）。

    段 0 用用户首帧；最后段用用户尾帧；中间段用上一段的尾帧作为下一段首帧
    （由 Director 内部处理，配合 continuityOverlapFrames 衔接）。
    """
    per_shot_frames = max(5, int(SHOT_MAX_SECONDS * frame_rate))
    n_shots = max(1, -(-total_frames // per_shot_frames))
    shots = []
    for i in range(n_shots):
        start = i * per_shot_frames
        end = min(total_frames, (i + 1) * per_shot_frames)
        frames = end - start
        if frames < 5:
            break
        is_first = i == 0
        is_last = i == n_shots - 1
        shots.append({
            "id": f"s{i}",
            "startImage": {"imageFile": first_ref} if is_first else {"imageFile": ""},
            "endImage": {"imageFile": last_ref} if (is_last and last_ref) else {"imageFile": ""},
            "durationSec": round(frames / max(1.0, frame_rate), 2),
        })
    return shots


def _timeline_data(*, first_ref: str, last_ref: str, global_prompt: str,
                   total_frames: int, frame_rate: float, width: int, height: int) -> str:
    """构建 FL2V timeline_data（多段 shots + 导演全局提示词 + 16:9）。"""
    shots = _build_shots(first_ref=first_ref, last_ref=last_ref,
                         total_frames=total_frames, frame_rate=frame_rate,
                         ref_max_size=width, width=width, height=height)
    timeline = {
        "version": 4,
        "editMode": "global",
        "timelineMode": "fl2v",
        "totalFrames": total_frames,
        "frameRate": float(frame_rate),
        "width": width,
        "height": height,
        "refMaxSize": width,
        "output": {
            "mode": "fixed",
            "longEdge": width,
            "width": width,
            "height": height,
            "maxExportFrames": 0,
            "exportMode": "all",
            "continuityEnabled": True,
            "continuityOverlapFrames": 9,
        },
        "shots": shots,
        "global": {
            "taskType": "fl2v — 首尾帧生视频(First-Last Frame)",
            "prompt": global_prompt,
            "refs": [],
            "referenceVideo": {},
            "continuousReference": False,
            "genImage": {"imageFile": ""},
        },
        "videoClips": [],
        "video": {
            "fileName": "", "videoFile": "", "subfolder": "", "type": "input",
            "frames": [], "frameMap": [],
        },
        "gen": {"defaultFrameCount": total_frames},
        "runSelectEnabled": False,
        "runSelection": [],
    }
    return json.dumps(timeline, ensure_ascii=False)


@dataclass
class MiniMaxH3Provider:
    """MiniMaxH3 FL2V 首尾帧 Provider（ComfyUI Native）。"""

    adapter: ComfyUIAdapter
    template: WorkflowTemplate
    provider_name: str = "minimax_h3"

    async def generate(
        self,
        start_frame: Path | str,
        end_frame: Path | str,
        prompt: str,
        duration: float,
        fps: int = 24,
        metadata: dict | None = None,
        width: int = 864,
        height: int = 480,
        seed: int = 42,
        output_path: Path | None = None,
    ) -> MediaArtifact:
        metadata = metadata or {}
        start_path = Path(start_frame)
        has_end = bool(end_frame) and Path(end_frame).is_file()
        if not start_path.is_file():
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                f"Frame image does not exist: {start_path}",
            )
        # 首帧上传；尾帧可选（i2v 续接模式）
        first_ref = await self.adapter.upload_image(start_path)
        last_ref = await self.adapter.upload_image(end_frame) if has_end else None
        total_frames = max(5, int(round(duration * fps)))
        # MiniMaxH3 长视频采样较慢：按时长放宽超时（10s FL2V+音频实测 >15min）
        self.adapter.timeout_seconds = max(self.adapter.timeout_seconds, int(duration * 120) + 600)
        if output_path is None:
            output_path = Path(f"outputs/minimax_h3/fl2v_{total_frames}f.mp4")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        timeline = _timeline_data(
            first_ref=first_ref.reference,
            last_ref=last_ref.reference if last_ref else "",
            global_prompt=prompt,
            total_frames=total_frames,
            frame_rate=float(fps),
            width=width,
            height=height,
        )
        workflow = self.template.render(
            global_prompt=prompt,
            seed=seed,
            frame_rate=float(fps),
            width=width,
            height=height,
            total_frames=total_frames,
            timeline_data=timeline,
            filename_prefix=f"minimax_h3/{output_path.stem}",
        )
        comfy_artifact = await self.adapter.generate_to_file(workflow, output_path)
        return MediaArtifact(
            path=output_path,
            kind="video",
            metadata={
                "provider": self.provider_name,
                "frames": total_frames,
                "duration_s": round(total_frames / fps, 2),
                "fps": fps,
                "width": width,
                "height": height,
                "seed": seed,
                "source_filename": getattr(comfy_artifact, "filename", ""),
                "first_frame": str(start_path),
                "last_frame": str(end_frame) if has_end else "",
                **metadata,
            },
        )
