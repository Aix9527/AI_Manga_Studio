import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from backend.production.comfy_adapter import (
    ComfyUIAdapter,
    ProductionError,
    ProductionErrorCode,
)


class ErrorHistoryServer:
    def __init__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self):
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @staticmethod
    def _handler():
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self._json({"prompt_id": "broken-prompt"})

            def do_GET(self):
                self._json(
                    {
                        "broken-prompt": {
                            "outputs": {},
                            "status": {
                                "status_str": "error",
                                "completed": False,
                                "messages": [
                                    [
                                        "execution_error",
                                        {
                                            "node_id": "1",
                                            "node_type": "CheckpointLoaderSimple",
                                            "exception_message": "header too small",
                                        },
                                    ]
                                ],
                            },
                        }
                    }
                )

            def log_message(self, format, *args):
                return

            def _json(self, payload):
                encoded = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        return Handler


@pytest.mark.asyncio
async def test_execution_error_is_raised_without_waiting_for_timeout(tmp_path):
    with ErrorHistoryServer() as fake:
        adapter = ComfyUIAdapter(
            base_url=fake.base_url,
            poll_interval=0.01,
            timeout_seconds=2,
        )

        with pytest.raises(ProductionError) as captured:
            await adapter.generate_to_file({}, tmp_path / "missing.png")

    assert captured.value.code is ProductionErrorCode.COMFY_EXECUTION_FAILED
    assert "header too small" in captured.value.message
