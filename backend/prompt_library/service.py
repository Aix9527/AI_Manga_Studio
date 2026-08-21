"""Prompt Library service（Phase 15.3-B：项目提示词库）.

基于 Higgsfield Hell Grind CINEDANCE skill 的 15 段视频提示词骨架 +
MiniMax H3 官方指南参数。提供模板读取 / 提示词组装（VideoPromptCompiler）。"""

from __future__ import annotations

import json
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"


class PromptLibrary:
    def __init__(self, assets: str | Path | None = None):
        self.assets = Path(assets) if assets else ASSETS
        self._template: dict | None = None

    def template(self) -> dict:
        if self._template is None:
            self._template = json.loads(
                (self.assets / "cinedance_template.json").read_text(encoding="utf-8"))
        return self._template

    # ------------------------------------------------------------ compile
    def compile_shot(self, *, characters: list[str], location: str,
                     action: str, duration_s: int, beats: list[str],
                     first_frame: str = "", optics: str = "",
                     camera: str = "", lighting: str = "",
                     audio: str = "", acting: str = "") -> str:
        """按 CINEDANCE 15 段骨架组装标准视频提示词。"""
        tpl = self.template()
        sections: list[str] = []
        sections.append("SCENE CONTEXT\n"
                        f"EXACT {len(characters)} CHARACTERS — NO DUPLICATES: {', '.join(characters)}. "
                        f"{action} 单段连续 {duration_s} 秒镜头，无剪辑。")
        if characters:
            refs = "\n".join(f"@{c} for character reference" for c in characters)
            sections.append("ACTIVE REFERENCES\n" + refs)
        sections.append("LOCATION MAP\n" + location)
        sections.append("FIRST FRAME AND SPATIAL BLOCKING\n" + (first_frame or "首帧为全景建立，无空镜头，无运镜。"))
        sections.append("FORMAT MODE\n" + f"单段连续 take，{duration_s} 秒，实时，无剪辑，无变速。")
        sections.append("OPTICS\n" + (optics or "≈40° 广角，机位胸口高度，景深覆盖全场景。"))
        sections.append("CAMERA\n" + (camera or "平静的呼吸式手持，保持构图；无推拉、无变焦、无甩镜。"))
        if beats:
            timing = "\n".join(beats)
            sections.append("ACTION TIMING\n" + timing)
        sections.append("PHYSICS\n道具与角色遵守真实重量与惯性；接触阴影正确；无漂浮道具。")
        sections.append("LIGHTING\n" + (lighting or "单一自然光源，逆光勾勒，暗部保留层次；无补光。"))
        sections.append("AUDIO\n" + (audio or "仅环境音（diegetic），无音乐。"))
        sections.append("CHARACTER ACTING\n" + (acting or "写行为而非情绪：状态 / 想要 / 隐藏 / 身体节奏 / 变化点。"))
        sections.append("STYLE\n" + tpl["style_prefix"])
        sections.append("QUALITY\n8K 细节，毛孔级皮肤，无抖动闪烁，所有面孔始终等于引用。")
        temporal = "\n".join(tpl.get("temporal_prompt_rules", []))
        sections.append("TEMPORAL STABILITY\n" + temporal)
        constraints = (f"恰好 {len(characters)} 人在画面中，无其他人；"
                       f"{duration_s} 秒全程；现在时，短句；只写肯定式动作；不写年龄。")
        sections.append("POSITIVE CONSTRAINTS\n" + constraints)
        sections.append("VIDEO NEGATIVE\n" + tpl.get("video_negative_prompt", ""))
        return "\n\n".join(sections)

    # ------------------------------------------------------------ queries
    def sections(self) -> list[dict]:
        return self.template()["sections"]

    def wording_rules(self) -> list[str]:
        return self.template()["wording_rules"]

    def style_prefix(self) -> str:
        return self.template()["style_prefix"]

    def minimax_params(self) -> dict:
        return self.template()["minimax_h3_params"]
