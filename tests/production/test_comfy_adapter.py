from pathlib import Path

import pytest

from backend.production.comfy_adapter import (
    ComfyUIAdapter,
    ProductionError,
    ProductionErrorCode,
)
from tests.fixtures.fake_comfy import FakeComfyServer


@pytest.mark.asyncio
async def test_generate_copies_real_history_output(tmp_path: Path):
    with FakeComfyServer() as fake:
        adapter = ComfyUIAdapter(
            base_url=fake.base_url,
            poll_interval=0.01,
            timeout_seconds=1,
        )
        target = tmp_path / "frame.png"

        artifact = await adapter.generate_to_file(
            {"1": {"class_type": "SaveImage"}},
            target,
        )

    assert target.read_bytes() == b"\x89PNG\r\n\x1a\nfixture"
    assert artifact.filename == "frame_00001_.png"


@pytest.mark.asyncio
async def test_generate_rejects_completed_history_without_outputs(tmp_path: Path):
    with FakeComfyServer(no_output=True) as fake:
        adapter = ComfyUIAdapter(
            base_url=fake.base_url,
            poll_interval=0.01,
            timeout_seconds=1,
        )

        with pytest.raises(ProductionError) as captured:
            await adapter.generate_to_file({}, tmp_path / "missing.png")

    assert captured.value.code is ProductionErrorCode.COMFY_NO_OUTPUT
