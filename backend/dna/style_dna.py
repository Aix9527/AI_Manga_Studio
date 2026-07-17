"""
V3.0 Layer 5 — Style DNA

Global style lock. Set at project initialization and immutable throughout the pipeline.
All Prompts and renders automatically inject StyleDNA parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StyleDNA:
    """Global style definition — locked for entire project.

    Once set, StyleDNA values are injected into every stage:
      - Prompt Engine: art_style, lighting, lens, depth_of_field
      - ComfyUI Workflow: resolution, aspect_ratio, color_grading
      - Final Render: lut_path, fps

    AI modules read StyleDNA but CANNOT modify it.
    """

    project_id: str

    # ── Visual Style ──────────────────────────────────────
    art_style: str = "国漫电影级"
    """Overall art direction: 国漫电影级/日式动画/写实/水墨/赛博朋克/油画"""

    lighting: str = "高动态光影"
    """Lighting style: 高动态光影/柔和体积光/戏剧性侧光/顶光/自然光"""

    color_grading: str = "青绿色调"
    """Color grading preset: 青绿色调/暖金色/冷蓝色/褪色胶片/高饱和动漫"""

    # ── Camera ────────────────────────────────────────────
    lens: str = "电影镜头"
    """Lens type: 电影镜头/广角/长焦/微距/鱼眼"""

    depth_of_field: str = "浅景深"
    """DOF: 浅景深/深景深/无"""

    # ── Output ────────────────────────────────────────────
    resolution: str = "3840x2160"
    """Output resolution: 3840x2160 / 1920x1080 / 2560x1440"""

    aspect_ratio: str = "16:9"
    """Aspect ratio: 16:9 / 21:9 / 4:3 / 9:16"""

    fps: int = 24
    """Frames per second for video output"""

    # ── Post-processing ───────────────────────────────────
    lut_path: str = ""
    """Path to LUT file applied at Final Render"""

    grain: float = 0.0
    """Film grain intensity (0.0 ~ 1.0)"""

    vignette: float = 0.0
    """Vignette intensity (0.0 ~ 1.0)"""

    # ── Composition ───────────────────────────────────────
    composition_style: str = "三分法"
    """Composition rule: 三分法/对称/对角线/引导线/框架构图"""

    character_spacing: str = "natural"
    """Character spacing: natural/close/distant"""

    # ── Motion ────────────────────────────────────────────
    motion_easing: str = "ease-in-out"
    """Animation easing: linear/ease-in/ease-out/ease-in-out/cubic-bezier"""

    transition_style: str = "dissolve"
    """Default transition: cut/dissolve/fade/wipe/slide"""

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "art_style": self.art_style,
            "lighting": self.lighting,
            "color_grading": self.color_grading,
            "lens": self.lens,
            "depth_of_field": self.depth_of_field,
            "resolution": self.resolution,
            "aspect_ratio": self.aspect_ratio,
            "fps": self.fps,
            "lut_path": self.lut_path,
            "grain": self.grain,
            "vignette": self.vignette,
            "composition_style": self.composition_style,
            "character_spacing": self.character_spacing,
            "motion_easing": self.motion_easing,
            "transition_style": self.transition_style,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StyleDNA":
        return cls(
            project_id=data.get("project_id", ""),
            art_style=data.get("art_style", "国漫电影级"),
            lighting=data.get("lighting", "高动态光影"),
            color_grading=data.get("color_grading", "青绿色调"),
            lens=data.get("lens", "电影镜头"),
            depth_of_field=data.get("depth_of_field", "浅景深"),
            resolution=data.get("resolution", "3840x2160"),
            aspect_ratio=data.get("aspect_ratio", "16:9"),
            fps=data.get("fps", 24),
            lut_path=data.get("lut_path", ""),
            grain=data.get("grain", 0.0),
            vignette=data.get("vignette", 0.0),
            composition_style=data.get("composition_style", "三分法"),
            character_spacing=data.get("character_spacing", "natural"),
            motion_easing=data.get("motion_easing", "ease-in-out"),
            transition_style=data.get("transition_style", "dissolve"),
        )

    def get_prompt_fragment(self) -> str:
        """Build the fixed Style portion of every generation prompt.

        This fragment is injected into EVERY prompt and CANNOT be modified by AI.
        """
        parts = [
            self.art_style,
            self.lighting,
            self.color_grading,
            self.lens,
            self.depth_of_field,
            f"{self.composition_style} composition",
            "masterpiece, best quality, highly detailed",
        ]
        return ", ".join(parts)

    def get_negative_fragment(self) -> str:
        """Build the global negative prompt fragment."""
        negatives = [
            "lowres", "bad quality", "blurry", "jpeg artifacts",
            "watermark", "signature", "text", "logo",
            "deformed", "disfigured", "ugly", "poorly drawn",
        ]
        if "动漫" in self.art_style or "日式" in self.art_style:
            negatives.append("photorealistic")
        return ", ".join(negatives)

    @classmethod
    def presets(cls) -> dict:
        """Available style presets."""
        return {
            "国漫电影": cls(
                project_id="preset",
                art_style="国漫电影级",
                lighting="高动态光影",
                color_grading="青绿色调",
                lens="电影镜头",
                depth_of_field="浅景深",
                composition_style="三分法",
            ),
            "日式动画": cls(
                project_id="preset",
                art_style="日式动画",
                lighting="柔和体积光",
                color_grading="高饱和动漫",
                lens="标准镜头",
                depth_of_field="深景深",
                composition_style="对称",
            ),
            "写实电影": cls(
                project_id="preset",
                art_style="写实电影级",
                lighting="戏剧性侧光",
                color_grading="褪色胶片",
                lens="电影镜头",
                depth_of_field="浅景深",
                composition_style="引导线",
            ),
            "赛博朋克": cls(
                project_id="preset",
                art_style="赛博朋克",
                lighting="霓虹灯光",
                color_grading="冷蓝色",
                lens="广角",
                depth_of_field="浅景深",
                composition_style="对角线",
            ),
        }
