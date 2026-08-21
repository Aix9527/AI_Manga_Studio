from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from backend.production.comfy_adapter import (
    ComfyUIAdapter,
    ProductionError,
    ProductionErrorCode,
)


class FakeUploadServer:
    def __init__(self, payload: dict[str, str]):
        self.payload = payload
        self.received_body = b""
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != "/upload/image":
                    self.send_error(404)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                outer.received_body = self.rfile.read(length)
                encoded = json.dumps(outer.payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format, *args):
                return

        return Handler


@pytest.mark.asyncio
async def test_upload_image_returns_safe_comfy_reference(tmp_path: Path):
    image = tmp_path / "keyframe.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    with FakeUploadServer(
        {"name": "keyframe.png", "subfolder": "novel_video", "type": "input"}
    ) as fake:
        adapter = ComfyUIAdapter(base_url=fake.base_url)

        uploaded = await adapter.upload_image(image)

    assert uploaded.reference == "novel_video/keyframe.png"
    assert uploaded.filename == "keyframe.png"
    assert b"fixture" in fake.received_body


@pytest.mark.asyncio
async def test_upload_image_rejects_traversal_in_comfy_response(tmp_path: Path):
    image = tmp_path / "keyframe.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    with FakeUploadServer(
        {"name": "../escape.png", "subfolder": "novel_video", "type": "input"}
    ) as fake:
        adapter = ComfyUIAdapter(base_url=fake.base_url)

        with pytest.raises(ProductionError) as captured:
            await adapter.upload_image(image)

    assert captured.value.code is ProductionErrorCode.COMFY_WORKFLOW_INVALID
