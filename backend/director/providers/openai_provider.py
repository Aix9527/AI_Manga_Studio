"""OpenAI director provider (Phase 10.7-B).

Cloud option for high-value shots; OpenAI-compatible chat completions.
Requires ``OPENAI_API_KEY``; silently unavailable otherwise.
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


class OpenAIDirectorProvider(DirectorProvider):
    name = "llm-openai"

    def __init__(self, api_key: str = "", base_url: str = "", model: str = ""):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL")
                         or "https://api.openai.com/v1").rstrip("/")
        self.model = model or os.environ.get("OPENAI_DIRECTOR_MODEL", "gpt-4o-mini")

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate_directive(
        self,
        shot: Shot,
        section_context: dict | None = None,
    ) -> ShotDirective:
        if not self.is_available:
            raise ProviderError("OPENAI_API_KEY not set")
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
            raise ProviderError(f"OpenAI director call failed: {exc}") from exc
        return parse_directive_json(content, shot, director_version=self.name)
