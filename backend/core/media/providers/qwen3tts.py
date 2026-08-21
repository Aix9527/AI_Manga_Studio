"""Qwen3TTS Provider（H3-13A.2 修订：按 smoke 验证规格）

- 模型：Qwen3-TTS-12Hz-1.7B-CustomVoice（已下载）
- 克隆：VoiceClone（ref_audio 30s 样本）→ 角色专属音色
- 无样本兜底：CustomVoice 内置说话人（Uncle_Fu 等）
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

from ...domain.ids import create_id
from .voice_provider import VoiceProvider

COMFY = "http://127.0.0.1:8188"

LOADER = {
    "model_repo": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "download_source": "ModelScope",
    "precision": "bf16",
    "attn_mode": "sdpa",
    "auto_download": True,
}

# 内置说话人映射（无克隆样本时兜底）
SPEAKERS = {
    "suwan": "Vivian (Chinese - Bright, Sharp, Young Female)",
    "fangjueming": "Uncle_Fu (Chinese - Deep, Mellow, Mature Male)",
    "chenye": "Uncle_Fu (Chinese - Deep, Mellow, Mature Male)",
    "zhaoyiming": "Dylan (Chinese Beijing - Clear, Natural Young Male)",
    "narrator": "Serena (Chinese - Warm, Soft, Young Female)",
}


class Qwen3TTSProvider(VoiceProvider):
    name = "qwen3tts"

    ASSET_ROOT = Path("outputs/voice_assets")

    def _asset_dir(self, character_id):
        return self.ASSET_ROOT / f"{character_id}_v1"

    def has_asset(self, character_id):
        p = self._asset_dir(character_id) / "reference.wav"
        return p.exists() and p.stat().st_size > 1000  # 有效样本（>1KB）

    def health(self):
        try:
            r = httpx.get(COMFY + "/system_stats", timeout=5, trust_env=False)
            return {"ok": r.status_code == 200, "engine": "comfyui_qwen3tts"}
        except Exception:
            return {"ok": False, "error": "comfyui unreachable"}

    def generate(self, request):
        """request: text, character_id, emotion, speed, reference_audio"""
        text = request.text
        char = request.character_id
        ref_audio = request.reference_audio or (str(self._asset_dir(char) / "reference.wav") if self.has_asset(char) else "")

        c = httpx.Client(trust_env=False, timeout=20)
        prompt = {
            "1": {"class_type": "Qwen3TTSLoader", "inputs": dict(LOADER)},
        }

        if ref_audio and os.path.exists(ref_audio):
            # 克隆模式（角色音色资产）
            prompt["4"] = {"class_type": "LoadAudio", "inputs": {"audio": ref_audio}}
            prompt["2"] = {
                "class_type": "Qwen3TTSVoiceClone",
                "inputs": {
                    "model_obj": ["1", 0],
                    "target_text": text,
                    "target_language": "Chinese",
                    "output_mode": "Concatenate (Merge)",
                    "seed": 20260810,
                    "ref_audio": ["4", 0],
                    "instruct": request.emotion or "",
                },
            }
        else:
            # 兜底：内置说话人
            speaker = SPEAKERS.get(char, "Serena (Chinese - Warm, Soft, Young Female)")
            prompt["2"] = {
                "class_type": "Qwen3TTSCustomVoice",
                "inputs": {
                    "model_obj": ["1", 0],
                    "text": text,
                    "speaker": speaker,
                    "language": "Chinese",
                    "output_mode": "Concatenate (Merge)",
                    "seed": 20260810,
                    "instruct": request.emotion or "",
                },
            }

        prompt["3"] = {"class_type": "SaveAudio", "inputs": {"audio": ["2", 0], "filename_prefix": "voice/qwen3tts"}}

        r = c.post(COMFY + "/prompt", json={"prompt": prompt}, timeout=15)
        d = r.json()
        return {
            "provider": self.name,
            "submitted": "prompt_id" in d,
            "clone_mode": bool(ref_audio and os.path.exists(ref_audio)),
            "prompt_id": d.get("prompt_id"),
            "error": d.get("error"),
        }

    def clone(self, request):
        return {"voice_asset": request.character_id, "status": "registered"}


qwen3tts_provider = Qwen3TTSProvider()
