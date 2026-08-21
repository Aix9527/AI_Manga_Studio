"""Voice Production OS · 统一 Schema（GPT 设计）"""
from typing import Optional

from pydantic import BaseModel



class VoiceGenerateRequest(BaseModel):
    """文本 → 语音 生成请求"""

    text: str

    character_id: str

    emotion: str = "neutral"

    speed: float = 1.0

    sample_rate: int = 24000

    provider: Optional[str] = None

    style: Optional[str] = None


class VoiceCloneRequest(BaseModel):
    """参考音频 → 角色声音资产"""

    character_id: str

    reference_audio: str

    language: str = "zh"


class VoiceGenerateResult(BaseModel):
    """生成结果"""

    audio_path: str

    duration: float

    provider: str

    voice_asset_id: Optional[str] = None


class VoiceRouteRequest(BaseModel):
    """路由请求"""

    scene_type: str = "dialogue"

    character_id: Optional[str] = None


class VoiceAssetInfo(BaseModel):
    """声音资产元数据"""

    id: str

    character_id: str

    provider: str

    reference_audio: str

    version: str = "v1"

    sha256: str = ""

    frozen: bool = False
