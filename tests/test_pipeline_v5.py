from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from backend.pipeline_v5 import PipelineV5, ShotPipelineResult
from backend.unified_shot import UnifiedShot


class FakeLastFrameGenerator:
    def generate_spec(self, cinematic_shot, first_frame_prompt=""):
        return SimpleNamespace(
            last_frame_prompt="same character reaches the final pose",
            seed=123,
            steps=4,
            cfg=1.0,
            resolution=[320, 180],
        )


class FakeWorkflowGenerator:
    def __init__(self):
        self.seen_shot = None

    def generate(self, shot):
        self.seen_shot = shot
        return {"9": {"inputs": {"filename_prefix": "last_frame"}, "class_type": "SaveImage"}}


class FakeComfyUI:
    def submit_workflow(self, workflow, wait=True):
        return {"images": [{"path": "D:/AI_Manga_Studio/output/test_last_frame.png"}]}


def test_generate_last_frame_submits_prompt_workflow_and_records_path():
    pipeline = PipelineV5.__new__(PipelineV5)
    pipeline.last_frame_gen = FakeLastFrameGenerator()
    pipeline.workflow_gen = FakeWorkflowGenerator()
    pipeline.comfyui = FakeComfyUI()

    shot = UnifiedShot(chapter=1, scene=1, shot=1, characters=["角色A"], background="雨夜街道")
    cinematic = pipeline._build_cinematic_shot(shot)
    result = ShotPipelineResult(image_path="D:/AI_Manga_Studio/output/test_first_frame.png", image_prompt="first frame prompt")

    updated = pipeline._generate_last_frame(shot, cinematic, result)

    assert updated.last_frame_prompt == "same character reaches the final pose"
    assert updated.last_frame_path.endswith("test_last_frame.png")
    assert "same character reaches the final pose" in pipeline.workflow_gen.seen_shot.extra["last_frame_prompt"]


def test_local_interpolated_video_renderer_creates_mp4(tmp_path: Path):
    from backend.local_video_renderer import create_interpolated_video

    first = tmp_path / "first.png"
    last = tmp_path / "last.png"
    output = tmp_path / "clip.mp4"
    Image.new("RGB", (96, 64), (240, 40, 40)).save(first)
    Image.new("RGB", (96, 64), (40, 80, 240)).save(last)

    created = create_interpolated_video(str(first), str(last), str(output), duration=0.5, fps=8)

    assert created == str(output)
    assert output.exists()
    assert output.stat().st_size > 1000
