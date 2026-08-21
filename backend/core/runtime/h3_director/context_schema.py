"""H3 Director 上下文 Schema（GPT 设计）"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReferenceItem:
    """单条参考项 → H3 ref_images[] 映射"""

    type: str                 # character | location | prop | last_frame
    id: str                   # 资产 id（suwan_v3 / lab_v2 / dna_machine_v1）
    ref: str = ""             # 参考文件路径（图片/视频/音频）
    source: str = "image"     # image | prompt（无图时用 prompt 生成）
    prompt: str = ""          # 无图时的描述
    priority: int = 1
    created_at: str = ""


@dataclass
class SceneVisualDNA:
    """Scene Visual DNA（Phase H3-8）"""

    location_id: str
    name: str = ""
    architecture: list = field(default_factory=list)
    lighting: list = field(default_factory=list)
    color: list = field(default_factory=list)
    camera: str = ""
    fixed_objects: list = field(default_factory=list)
    description: str = ""


@dataclass
class ShotEndingState:
    """镜头结束状态（Phase H3-9 Shot Continuity Chain）"""

    shot_id: str
    character_pose: str = ""
    camera_position: str = ""
    lighting_state: str = ""
    note: str = ""
    ended_at: str = ""


@dataclass
class ReferencePackage:
    """Reference Package → H3 Omni Reference 输入"""

    shot_id: str
    ref_images: list = field(default_factory=list)   # list[ReferenceItem]
    ref_videos: list = field(default_factory=list)
    ref_audios: list = field(default_factory=list)
    scene_dna: dict = field(default_factory=dict)    # SceneVisualDNA as dict
    previous_shot_state: dict = field(default_factory=dict)
