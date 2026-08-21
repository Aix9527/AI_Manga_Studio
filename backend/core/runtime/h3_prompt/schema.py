"""H3 Prompt Template Schema（GPT 设计）"""
from typing import List, Optional

from pydantic import BaseModel


class TemplateConstraints(BaseModel):
    """模板约束"""

    camera: List[str] = []

    lighting: List[str] = []

    audio: List[str] = []

    forbidden: List[str] = []


class H3PromptTemplate(BaseModel):
    """H3 提示词模板（GPT schema）"""

    id: str

    title: str

    category: str

    tags: List[str] = []

    # 推荐 H3 模式
    workflow: str = "standard"  # standard | reference

    aspect_ratio: str = "16:9"

    duration_s: int = 15

    style_hint: str = ""

    prompt_template: str = ""

    placeholders: List[str] = []

    constraints: TemplateConstraints = TemplateConstraints()
