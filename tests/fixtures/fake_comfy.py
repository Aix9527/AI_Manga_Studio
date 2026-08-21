import json
import re
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


class FakeComfyServer:
    """Small HTTP ComfyUI fake that exposes terminal video history for tests."""

    def __init__(
        self,
        no_output: bool = False,
        terminal_entry: dict | None = None,
    ):
        self.no_output = no_output
        self.terminal_entry = terminal_entry
        self.last_prompt_id = "prompt-1"
        self.last_prompt = {}
        self.uploaded_filenames: list[str] = []
        self.uploaded_payloads: list[bytes] = []
        self.history_requests = 0
        self.queue_running: list[str] = []
        self.queue_pending: list[str] = []
        self.queue_snapshots: list[dict[str, list[str]]] = []
        self.queue_handoff_after_read_to: str | None = None
        self.cancelled_prompts: set[str] = set()
        self.interrupts = 0
        self._media_dir = tempfile.TemporaryDirectory()
        self.video_payload = self._make_video_payload(Path(self._media_dir.name))
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
        self._media_dir.cleanup()

    @staticmethod
    def _make_video_payload(directory: Path) -> bytes:
        """Create a short video with audio so provider tests use real media evidence."""
        video = directory / "fixture.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=s=864x480:r=24",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=880:sample_rate=44100",
                "-t",
                "5.1",
                "-c:v",
                "mpeg4",
                "-c:a",
                "aac",
                "-shortest",
                str(video),
            ],
            check=True,
            capture_output=True,
        )
        return video.read_bytes()

    def _handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path == "/prompt":
                    length = int(self.headers.get("Content-Length", "0"))
                    outer.last_prompt = json.loads(self.rfile.read(length)) ["prompt"]
                    self._json({"prompt_id": outer.last_prompt_id})
                    return
                if self.path == "/upload/image":
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = self.rfile.read(length)
                    filename = re.search(br'filename="([^"]+)"', payload)
                    name = filename.group(1).decode("utf-8") if filename else "upload.png"
                    outer.uploaded_filenames.append(name)
                    if filename is None:
                        outer.uploaded_payloads.append(b"")
                    else:
                        body_start = payload.find(b"\r\n\r\n", filename.end())
                        body_end = payload.find(b"\r\n--", body_start + 4)
                        outer.uploaded_payloads.append(
                            payload[body_start + 4 : body_end]
                            if body_start >= 0 and body_end >= 0
                            else b""
                        )
                    self._json(
                        {"name": name, "subfolder": "novel_video", "type": "input"}
                    )
                    return
                if self.path == "/queue":
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    deleted = set(payload.get("delete", []))
                    outer.queue_pending = [item for item in outer.queue_pending if item not in deleted]
                    self._json({"deleted": sorted(deleted)})
                    return
                if self.path == "/interrupt":
                    outer.interrupts += 1
                    outer.cancelled_prompts.update(outer.queue_running)
                    outer.queue_running.clear()
                    self._json({"interrupted": True})
                    return
                self.send_error(404)

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path == "/queue":
                    if outer.queue_snapshots:
                        snapshot = outer.queue_snapshots.pop(0)
                        outer.queue_running = list(snapshot.get("queue_running", []))
                        outer.queue_pending = list(snapshot.get("queue_pending", []))
                    self._json({
                        "queue_running": [[index, prompt] for index, prompt in enumerate(outer.queue_running)],
                        "queue_pending": [[index, prompt] for index, prompt in enumerate(outer.queue_pending)],
                    })
                    if outer.queue_handoff_after_read_to is not None:
                        outer.queue_running = [outer.queue_handoff_after_read_to]
                        outer.queue_handoff_after_read_to = None
                    return
                if parsed.path.startswith("/history/"):
                    prompt_id = parsed.path.rsplit("/", 1)[-1]
                    outer.history_requests += 1
                    if prompt_id in outer.cancelled_prompts:
                        self._json({prompt_id: {"outputs": {}, "status": {"status_str": "cancelled", "completed": True}}})
                        return
                    if prompt_id != outer.last_prompt_id:
                        self._json({})
                        return
                    if outer.terminal_entry is not None:
                        self._json({outer.last_prompt_id: outer.terminal_entry})
                        return
                    if outer.history_requests == 1:
                        self._json(
                            {
                                outer.last_prompt_id: {
                                    "outputs": {},
                                    "status": {
                                        "status_str": "executing",
                                        "completed": False,
                                    },
                                }
                            }
                        )
                        return
                    outputs = {}
                    if not outer.no_output:
                        outputs = (
                            {
                                "24": {
                                    "videos": [
                                        {
                                            "filename": "segment.mp4",
                                            "subfolder": "",
                                            "type": "output",
                                        }
                                    ]
                                }
                            }
                            if any(
                                node.get("class_type") == "SaveVideo"
                                for node in outer.last_prompt.values()
                            )
                            else {
                                "9": {
                                    "images": [
                                        {
                                            "filename": "frame_00001_.png",
                                            "subfolder": "",
                                            "type": "output",
                                        }
                                    ]
                                }
                            }
                        )
                        entry = {
                            "outputs": outputs,
                            "status": {"status_str": "success", "completed": True},
                        }
                    else:
                        entry = {
                            "outputs": outputs,
                            "status": {"status_str": "success", "completed": True},
                        }
                    self._json({outer.last_prompt_id: entry})
                    return
                if parsed.path == "/view":
                    payload = (
                        outer.video_payload
                        if "filename=segment.mp4" in parsed.query
                        else b"\x89PNG\r\n\x1a\nfixture"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                self.send_error(404)

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
