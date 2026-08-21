"""Qwen director provider (Phase 10.7-B).

Default local/cloud choice: DashScope OpenAI-compatible endpoint, or any
OpenAI-compatible local Qwen server via ``QWEN_BASE_URL``.  Requires
``QWEN_API_KEY`` / ``DASHSCOPE_API_KEY``; silently unavailable otherwise so
the HybridDirector falls back to the rule provider.
"""

from __future__ import annotations

import os

from backend.agents.director_v2 import ShotDirective
from backend.director.providers.base import (
    DIRECTOR_SCHEMA_PROMPT,
    DirectorProvider,
    ProviderError,
    director_user_prompt,
    parse_directive_json,
)
from backend.story.models import Shot


class QwenDirectorProvider(DirectorProvider):
    name = "llm-qwen"

    def __init__(self, api_key: str = "", base_url: str = "", model: str = ""):
        self.api_key = api_key or os.environ.get("QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY", "")
        self.base_url = (base_url or os.environ.get("QWEN_BASE_URL")
                         or "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
        self.model = model or os.environ.get("QWEN_DIRECTOR_MODEL", "qwen-plus")

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate_directive(
        self,
        shot: Shot,
        section_context: dict | None = None,
    ) -> ShotDirective:
        if not self.is_available:
            raise ProviderError("QWEN_API_KEY not set")
        import httpx

        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": DIRECTOR_SCHEMA_PROMPT},
                        {"role": "user", "content": director_user_prompt(shot, section_context)},
                    ],
                    "temperature": 0.4,
                    "response_format": {"type": "json_object"},
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001 - fall back to rule on any failure
            raise ProviderError(f"Qwen director call failed: {exc}") from exc
        return parse_directive_json(content, shot, director_version=self.name)

