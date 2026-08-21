from __future__ import annotations

import pytest

from backend.production.comfy_adapter import ComfyUIAdapter
from tests.fixtures.fake_comfy import FakeComfyServer


@pytest.mark.asyncio
@pytest.mark.parametrize("running", [False, True])
async def test_cancel_job_verifies_exact_prompt_left_live_queue(running):
    with FakeComfyServer() as server:
        if running:
            server.queue_running = ["prompt-1"]
        else:
            server.queue_pending = ["prompt-1", "other-prompt"]
        result = await ComfyUIAdapter(server.base_url).cancel_job("prompt-1")

        assert result.state == ("uncertain" if running else "verified_cancelled")
        assert result.was_running is running
        assert "other-prompt" in server.queue_pending if not running else True
        assert server.interrupts == 0


@pytest.mark.asyncio
async def test_cancel_job_does_not_interrupt_prompt_that_took_over_running_slot():
    """A global interrupt must not hit the next job during prompt handoff."""
    with FakeComfyServer() as server:
        server.last_prompt_id = "prompt-with-history"
        server.queue_snapshots = [
            {"queue_running": ["prompt-1"], "queue_pending": []},
            {"queue_running": ["prompt-2"], "queue_pending": []},
        ]

        result = await ComfyUIAdapter(server.base_url).cancel_job("prompt-1")

        assert result.state == "uncertain"
        assert result.was_running is True
        assert server.interrupts == 0


@pytest.mark.asyncio
async def test_cancel_job_never_globally_interrupts_next_prompt_during_live_handoff():
    """A target may leave the running slot immediately after the final queue read."""
    with FakeComfyServer() as server:
        server.last_prompt_id = "different-prompt"
        server.queue_running = ["prompt-1"]
        server.queue_handoff_after_read_to = "prompt-2"

        result = await ComfyUIAdapter(server.base_url).cancel_job("prompt-1")

        assert result.state == "uncertain"
        assert result.was_running is True
        assert server.interrupts == 0
        assert server.queue_running == ["prompt-2"]
        assert "prompt-2" not in server.cancelled_prompts


@pytest.mark.asyncio
async def test_cancel_job_running_prompt_requires_history_confirmed_cancellation():
    with FakeComfyServer() as server:
        server.queue_running = ["prompt-1"]
        server.terminal_entry = {
            "outputs": {},
            "status": {"status_str": "cancelled", "completed": True},
        }

        result = await ComfyUIAdapter(server.base_url).cancel_job("prompt-1")

        assert result.state == "verified_cancelled"
        assert result.was_running is True
        assert server.interrupts == 0
        assert server.history_requests >= 1
