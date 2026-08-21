"""Claude director provider (Phase 10.7-B).

Cloud option for complex drama; Anthropic Messages API.  Requires
``ANTHROPIC_API_KEY``; silently unavailable otherwise.
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


class ClaudeDirectorProvider(DirectorProvider):
    name = "llm-claude"

    def __init__(self, api_key: str = "", base_url: str = "", model: str = ""):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = (base_url or os.environ.get("ANTHROPIC_BASE_URL")
                         or "https://api.anthropic.com").rstrip("/")
        self.model = model or os.environ.get("CLAUDE_DIRECTOR_MODEL", "claude-sonnet-4-5")

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate_directive(
        self,
        shot: Shot,
        section_context: dict | None = None,
    ) -> ShotDirective:
        if not self.is_available:
            raise ProviderError("ANTHROPIC_API_KEY not set")
        import httpx

        try:
            resp = httpx.post(
                f"{self.base_url}/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 1200,
                    "temperature": 0.4,
                    "system": DIRECTOR_SCHEMA_PROMPT,
                    "messages": [
                        {"role": "user", "content": director_user_prompt(shot, section_context)},
                    ],
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            content = resp.json()["content"][0]["text"]
        except Exception as exc:  # noqa: BLE001 - fall back to rule on any failure
            raise ProviderError(f"Claude director call failed: {exc}") from exc
        return parse_directive_json(content, shot, director_version=self.name)
