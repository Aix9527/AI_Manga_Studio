"""Phase 15.3-E：MiniMaxH3 长视频（3-5 分钟）多段流式续帧生成.

MiniMaxH3 单次训练范围 5-15 秒。长视频方案：
- 每段 15s（FL2V 或从上一段尾帧续接）
- 段间提取尾帧作为下一段首帧（流式续帧，保证连续性）
- 最后一段锁定用户尾帧
- ffmpeg concat 拼接 → 3-5 分钟成片
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from backend.production.comfy_adapter import ComfyUIAdapter
from backend.production.workflow_templates import WorkflowTemplate
from backend.video.providers.minimax_h3_provider import MiniMaxH3Provider, SHOT_MAX_SECONDS

WORKFLOW = "minimax_h3_fl2va_native.json"


def _extract_last_frame(video: Path, out_png: Path) -> Path:
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        exe = "ffmpeg"
    subprocess.run([exe, "-y", "-v", "error", "-sseof", "-0.2", "-i", str(video),
                    "-frames:v", "1", str(out_png)], check=True, timeout=30)
    return out_png


def _concat_videos(parts: list[Path], output: Path) -> Path:
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        exe = "ffmpeg"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        lst = Path(tmp) / "list.txt"
        lines = [f"file '{p.as_posix()}'" for p in parts]
        lst.write_text("\n".join(lines), encoding="utf-8")
        subprocess.run([exe, "-y", "-v", "error", "-f", "concat", "-safe", "0",
                        "-i", str(lst), "-c", "copy", str(output)], check=True, timeout=120)
    return output


class MiniMaxLongVideoGenerator:
    """3-5 分钟长视频：15s/段流式续帧 + 拼接。"""

    def __init__(self, root: str = "storage", fps: int = 24,
                 width: int = 864, height: int = 480):
        self.fps = fps
        self.width = width
        self.height = height
        adapter = ComfyUIAdapter(timeout_seconds=3600)
        template = WorkflowTemplate.load(f"backend/production/workflows/{WORKFLOW}")
        self.provider = MiniMaxH3Provider(adapter=adapter, template=template)

    async def generate(self, *, start_frame: str, end_frame: str, prompt: str = "",
                       shots_prompts: list[str] | None = None,
                       duration_seconds: int = 15, shot_seconds: int = 5,
                       duration_minutes: int = 0, output_path: str) -> dict:
        """生成多段镜头并拼接。

        duration_seconds（默认 15s）+ shot_seconds（默认 5s/镜）→ 15s 视频
        内含至少 3 个镜头（每 5 秒一个）；duration_minutes 兼容长视频模式。
        """
        total_seconds = duration_minutes * 60 if duration_minutes > 0 else duration_seconds
        n_shots = max(1, -(-total_seconds // int(shot_seconds)))   # ceil
        parts: list[Path] = []
        current_start = Path(start_frame)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for i in range(n_shots):
                is_last = i == n_shots - 1
                remaining = total_seconds - i * int(shot_seconds)
                shot_duration = min(shot_seconds, remaining)
                shot_out = tmp_dir / f"part_{i:02d}.mp4"
                seg_start = str(current_start)
                seg_end = end_frame if is_last else ""
                shot_prompt = (shots_prompts[i] if shots_prompts and i < len(shots_prompts) else prompt)
                artifact = await self.provider.generate(
                    start_frame=seg_start,
                    end_frame=seg_end,
                    prompt=shot_prompt,
                    duration=shot_duration,
                    fps=self.fps,
                    width=self.width,
                    height=self.height,
                    output_path=shot_out,
                )
                parts.append(Path(artifact.path))
                print(f"  [long] part {i + 1}/{n_shots} done ({shot_duration}s)", flush=True)
                if not is_last:
                    # 取本段尾帧作为下一段首帧（流式续帧）
                    current_start = _extract_last_frame(
                        Path(artifact.path), tmp_dir / f"next_{i:02d}.png")
            output = _concat_videos(parts, Path(output_path))
        return {
            "video_path": str(output),
            "size_bytes": output.stat().st_size,
            "duration_seconds": total_seconds,
            "duration_minutes": duration_minutes,
            "shots": n_shots,
            "shot_seconds": shot_seconds,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
        }
