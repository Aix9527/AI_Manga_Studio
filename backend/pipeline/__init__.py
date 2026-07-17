"""
AI Manga Studio Pro V3.0 — 18-Layer Pipeline Modules

L7:  model_router    — Automatic model routing (Flux/SDXL/NoobAI/SUPIR/CodeFormer/Wan2.2/Hunyuan/LTX)
L8:  control_layer   — OpenPose + Depth + Lineart three-in-one ControlNet
L9:  image_pipeline  — Flux→PuLID→SUPIR→CodeFormer cascade
L10: quality_engine  — 15-dimension quality scoring (A/B/C/Fail)
L11: motion_planner  — Camera/wind/particle motion parameters from beat
L12: video_pipeline  — I2V→Optical Flow→RIFE frame interpolation
L13: lip_sync        — CosyVoice→MuseTalk→Emotion Overlay
L14: timeline        — Auto transitions + FFmpeg single-pass render
L16: multi_gpu       — Multi-GPU dispatch scheduler
"""

from backend.pipeline.model_router import ModelRouter
from backend.pipeline.control_layer import ControlLayer
from backend.pipeline.image_pipeline import ImagePipeline
from backend.pipeline.quality_engine import QualityEngine
from backend.pipeline.motion_planner import MotionPlanner
from backend.pipeline.video_pipeline import VideoPipeline
from backend.pipeline.lip_sync import LipSyncPipeline
from backend.pipeline.timeline import TimelineBuilder
from backend.pipeline.multi_gpu import MultiGPUScheduler

__all__ = [
    "ModelRouter",
    "ControlLayer",
    "ImagePipeline",
    "QualityEngine",
    "MotionPlanner",
    "VideoPipeline",
    "LipSyncPipeline",
    "TimelineBuilder",
    "MultiGPUScheduler",
]
