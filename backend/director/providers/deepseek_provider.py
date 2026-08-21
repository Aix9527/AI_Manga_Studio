"""DeepSeek director provider (Phase 12.7-B, GPT spec).

OpenAI-compatible chat completions against the DeepSeek API.  Requires
``DEEPSEEK_API_KEY``; silently unavailable otherwise so the arena runner
falls back to the deterministic simulated director in dry-runs.
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


class DeepSeekDirectorProvider(DirectorProvider):
    name = "llm-deepseek"

    def __init__(self, api_key: str = "", base_url: str = "", model: str = ""):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = (
            base_url
            or os.environ.get("DEEPSEEK_BASE_URL")
            or "https://api.deepseek.com/v1"
        ).rstrip("/")
        self.model = model or os.environ.get("DEEPSEEK_DIRECTOR_MODEL", "deepseek-chat")

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate_directive(
        self,
        shot: Shot,
        section_context: dict | None = None,
    ) -> ShotDirective:
        if not self.is_available:
            raise ProviderError("DEEPSEEK_API_KEY not set")
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
            return parse_directive_json(content, shot, director_version=self.name)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - network/HTTP -> fallback
            raise ProviderError(f"deepseek director failed: {exc}") from exc
