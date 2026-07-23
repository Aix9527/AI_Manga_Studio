
"""Fake image provider for development and testing."""

import uuid
from typing import Any

from backend.modules.generation.infrastructure.adapters.base import (
    GenerationProvider,
    ProviderRequest,
    ProviderResult,
)


class FakeImageProvider(GenerationProvider):
    @property
    def provider_id(self) -> str:
        return "fake-image"

    async def submit(self, request: ProviderRequest) -> ProviderResult:
        task_id = f"fake-{uuid.uuid4().hex[:12]}"
        return ProviderResult(
            remote_task_id=task_id,
            status="completed",
            outputs=[{
                "image_url": f"https://fake.local/output/{task_id}.png",
                "content_hash": f"sha256:fake_{uuid.uuid4().hex[:16]}",
                "metadata": {"prompt": request.prompt, "fake": True}
            }],
            metadata={"provider": "fake-image", "instant": True},
        )

    async def status(self, remote_task_id: str) -> ProviderResult:
        return ProviderResult(
            remote_task_id=remote_task_id,
            status="completed",
            outputs=[],
            metadata={},
        )

    async def cancel(self, remote_task_id: str) -> bool:
        return True

    async def reconcile(self, remote_task_id: str) -> ProviderResult:
        return await self.status(remote_task_id)

    async def health(self) -> dict[str, Any]:
        return {"status": "healthy", "provider": "fake-image"}

    def capabilities(self) -> list[str]:
        return ["text_to_image", "image_to_image", "character_generation"]
