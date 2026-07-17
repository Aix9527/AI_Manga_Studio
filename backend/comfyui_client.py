"""
AI Manga Studio Pro V1.0 — ComfyUI Client

Thin API client for communicating with ComfyUI's REST API.
Handles workflow submission, polling for completion, and
result retrieval. Supports both synchronous and asynchronous
execution patterns.

API Reference:
    POST /prompt          → Submit workflow
    GET  /history/{id}    → Get execution history
    GET  /queue           → View current queue status
    GET  /object_info     → List available node types
    GET  /view            → Retrieve generated media
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import requests
from loguru import logger

from backend.config import get_config


# ============================================================
# Data Classes
# ============================================================

@dataclass
class ComfyUIJob:
    """Represents a submitted ComfyUI job."""
    prompt_id: str
    status: str = "pending"  # pending, running, done, error
    result: Optional[Dict[str, Any]] = None
    error: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0


@dataclass
class ComfyUINodeInfo:
    """Metadata about a ComfyUI node type."""
    name: str = ""
    display_name: str = ""
    category: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: List[str] = field(default_factory=list)


@dataclass
class ComfyUIQueueStatus:
    """Current queue status."""
    running: int = 0
    pending: int = 0
    done: int = 0
    failed: int = 0


# ============================================================
# ComfyUI Client
# ============================================================

class ComfyUIClient:
    """HTTP client for ComfyUI server API."""

    DEFAULT_BASE_URL: str = "http://127.0.0.1:8188"
    DEFAULT_TIMEOUT: int = 30
    DEFAULT_POLL_INTERVAL: float = 2.0
    DEFAULT_MAX_WAIT: int = 600  # 10 minutes max wait per job

    def __init__(
        self,
        base_url: str = "",
        timeout: int = 30,
        poll_interval: float = 2.0,
        max_wait: int = 600,
    ) -> None:
        """Initialize the ComfyUI client.

        Args:
            base_url: ComfyUI server base URL.
            timeout: HTTP request timeout in seconds.
            poll_interval: Polling interval for job status.
            max_wait: Max wait time per job in seconds.
        """
        settings = get_config()
        self.base_url = (base_url or settings.comfyui.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.max_wait = max_wait

        # Session with retry
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        # Track submitted jobs
        self._jobs: Dict[str, ComfyUIJob] = {}

        # Output directories
        self.comfyui_output_dir = settings.comfyui.output_dir or ""

        self._connected = False
        logger.info(f"ComfyUIClient: Connected to {self.base_url}")

    # ----------------------------------------------------------
    # Connection Check
    # ----------------------------------------------------------

    def check_connection(self) -> Tuple[bool, str]:
        """Check if ComfyUI server is reachable.

        Returns:
            Tuple of (is_connected, message).
        """
        try:
            resp = self.session.get(
                f"{self.base_url}/object_info",
                timeout=5,
            )
            if resp.status_code == 200:
                data = json.loads(resp.content.lstrip(b'\xef\xbb\xbf').decode('utf-8'))
                node_count = len(data) if isinstance(data, dict) else 0
                self._connected = True
                return True, f"ComfyUI online ({node_count} node types)"
            return False, f"Unexpected status: {resp.status_code}"
        except requests.exceptions.ConnectionError:
            self._connected = False
            return False, "Connection refused — ComfyUI not running"
        except requests.exceptions.Timeout:
            self._connected = False
            return False, "Connection timeout"
        except Exception as e:
            self._connected = False
            return False, str(e)

    @property
    def is_connected(self) -> bool:
        """Check if ComfyUI is connected."""
        return self._connected

    # ----------------------------------------------------------
    # Workflow Submission
    # ----------------------------------------------------------

    def submit_workflow(
        self,
        workflow: Dict[str, Any],
        wait: bool = True,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Submit a workflow to ComfyUI.

        Args:
            workflow: ComfyUI workflow dict (API format).
            wait: Whether to wait for completion.
            extra_data: Extra data (client_id, etc.).

        Returns:
            Result dict from history, or None.
        """
        prompt_id = str(uuid.uuid4())

        payload: Dict[str, Any] = {
            "prompt": workflow,
            "client_id": prompt_id,
        }
        if extra_data:
            payload["extra_data"] = extra_data

        logger.info(f"ComfyUIClient: Submitting workflow (prompt_id={prompt_id})")

        try:
            resp = self.session.post(
                f"{self.base_url}/prompt",
                json=payload,
                timeout=self.timeout,
            )

            if resp.status_code != 200:
                logger.error(f"ComfyUIClient: Submission failed ({resp.status_code}): {resp.text}")
                return None

            data = json.loads(resp.content.lstrip(b'\xef\xbb\xbf').decode('utf-8'))

            # ComfyUI may return a different prompt_id
            actual_id = data.get("prompt_id", prompt_id)
            job = ComfyUIJob(prompt_id=actual_id, status="running")
            self._jobs[actual_id] = job

            if not wait:
                return {"prompt_id": actual_id, "status": "running"}

            # Poll for completion
            return self._wait_for_job(actual_id)

        except Exception as e:
            logger.error(f"ComfyUIClient: Submission error: {e}")
            return None

    def submit_workflow_file(
        self,
        workflow_path: str,
        wait: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Submit a workflow from a JSON file.

        Args:
            workflow_path: Path to workflow JSON.
            wait: Whether to wait for completion.

        Returns:
            Result dict or None.
        """
        if not os.path.exists(workflow_path):
            logger.error(f"ComfyUIClient: Workflow file not found: {workflow_path}")
            return None

        with open(workflow_path, "r", encoding="utf-8") as f:
            workflow = json.load(f)

        return self.submit_workflow(workflow, wait=wait)

    # ----------------------------------------------------------
    # Job Status
    # ----------------------------------------------------------

    def _wait_for_job(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Poll ComfyUI until job completes.

        Args:
            prompt_id: Prompt ID.

        Returns:
            Result dict or None.
        """
        start = time.time()
        last_poll = start

        logger.info(f"ComfyUIClient: Waiting for job {prompt_id}...")

        while time.time() - start < self.max_wait:
            # Throttle polling
            if time.time() - last_poll < self.poll_interval:
                time.sleep(0.1)
                continue

            last_poll = time.time()

            try:
                resp = self.session.get(
                    f"{self.base_url}/history/{prompt_id}",
                    timeout=(10, 30),
                )

                if resp.status_code != 200:
                    continue

                try:
                    data = json.loads(resp.content.lstrip(b'\xef\xbb\xbf').decode('utf-8'))
                except ValueError:
                    continue  # Malformed JSON from ComfyUI, retry
                history = data.get(prompt_id)

                if history is None:
                    continue  # Not yet available

                status = history.get("status", {})

                if status.get("status_str") == "error":
                    job = self._jobs.get(prompt_id)
                    if job:
                        job.status = "error"
                        job.error = str(status)
                        job.completed_at = time.time()
                    logger.error(f"ComfyUIClient: Job {prompt_id} failed: {status}")
                    return None

                if status.get("completed", False):
                    outputs = history.get("outputs", {})
                    result = self._extract_outputs(outputs)

                    job = self._jobs.get(prompt_id)
                    if job:
                        job.status = "done"
                        job.result = result
                        job.completed_at = time.time()

                    elapsed = time.time() - start
                    logger.info(f"ComfyUIClient: Job {prompt_id} complete ({elapsed:.1f}s)")
                    return result

            except requests.exceptions.RequestException:
                continue  # Transient error, keep polling

        logger.warning(f"ComfyUIClient: Job {prompt_id} timed out after {self.max_wait}s")
        return None

    def _extract_outputs(self, outputs: Dict) -> Dict[str, Any]:
        """Extract output file paths from history data.

        Args:
            outputs: History outputs dict.

        Returns:
            Simplified result dict.
        """
        result: Dict[str, Any] = {"images": [], "videos": [], "raw": outputs}

        for node_id, node_output in outputs.items():
            # Images
            images = node_output.get("images", [])
            for img in images:
                filename = img.get("filename", "")
                subfolder = img.get("subfolder", "")
                output_type = img.get("type", "output")

                if self.comfyui_output_dir:
                    full_path = os.path.join(self.comfyui_output_dir, subfolder, filename)
                else:
                    full_path = filename

                result["images"].append({
                    "filename": filename,
                    "subfolder": subfolder,
                    "type": output_type,
                    "path": full_path,
                })

            # GIFs / Videos
            gifs = node_output.get("gifs", [])
            for gif in gifs:
                result["videos"].append(gif)

        # Flatten single image result
        if len(result.get("images", [])) == 1:
            result["output"] = result["images"][0]["path"]
        elif result.get("images"):
            result["output"] = result["images"][0]["path"]

        return result

    # ----------------------------------------------------------
    # Queue Management
    # ----------------------------------------------------------

    def get_queue_status(self) -> ComfyUIQueueStatus:
        """Get current ComfyUI queue status.

        Returns:
            ComfyUIQueueStatus.
        """
        try:
            resp = self.session.get(
                f"{self.base_url}/queue",
                timeout=5,
            )
            if resp.status_code == 200:
                data = json.loads(resp.content.lstrip(b'\xef\xbb\xbf').decode('utf-8'))
                return ComfyUIQueueStatus(
                    running=len(data.get("queue_running", [])),
                    pending=len(data.get("queue_pending", [])),
                )
        except Exception as e:
            logger.debug(f"ComfyUIClient: Queue status query failed: {e}")

        return ComfyUIQueueStatus()

    def clear_queue(self) -> bool:
        """Clear the ComfyUI queue.

        Returns:
            True if successful.
        """
        try:
            resp = self.session.post(
                f"{self.base_url}/queue",
                json={"clear": True},
                timeout=5,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"ComfyUIClient: Clear queue failed: {e}")
            return False

    def cancel_current(self) -> bool:
        """Cancel the currently running job.

        Returns:
            True if successful.
        """
        try:
            resp = self.session.post(
                f"{self.base_url}/interrupt",
                timeout=5,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"ComfyUIClient: Interrupt failed: {e}")
            return False

    # ----------------------------------------------------------
    # Node Info
    # ----------------------------------------------------------

    def get_object_info(self) -> Dict[str, ComfyUINodeInfo]:
        """Get all available node types from ComfyUI.

        Returns:
            Dict of node_name → ComfyUINodeInfo.
        """
        result: Dict[str, ComfyUINodeInfo] = {}

        try:
            resp = self.session.get(
                f"{self.base_url}/object_info",
                timeout=10,
            )
            if resp.status_code != 200:
                return result

            data = json.loads(resp.content.lstrip(b'\xef\xbb\xbf').decode('utf-8'))
            for name, info in data.items():
                result[name] = ComfyUINodeInfo(
                    name=name,
                    display_name=info.get("display_name", name),
                    category=info.get("category", ""),
                    inputs=info.get("input", {}).get("required", {}),
                    outputs=info.get("output", []),
                )
        except Exception as e:
            logger.debug(f"ComfyUIClient: Object info failed: {e}")

        return result

    # ----------------------------------------------------------
    # Media Retrieval
    # ----------------------------------------------------------

    def get_image(
        self,
        filename: str,
        subfolder: str = "",
        output_type: str = "output",
    ) -> Optional[bytes]:
        """Retrieve a generated image.

        Args:
            filename: Image filename.
            subfolder: Subfolder name.
            output_type: Output type ('output' or 'temp').

        Returns:
            Image bytes or None.
        """
        params = {
            "filename": filename,
            "subfolder": subfolder,
            "type": output_type,
        }

        try:
            resp = self.session.get(
                f"{self.base_url}/view",
                params=params,
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.content
        except Exception as e:
            logger.error(f"ComfyUIClient: Image retrieval failed: {e}")

        return None

    def download_image(
        self,
        filename: str,
        save_path: str,
        subfolder: str = "",
        output_type: str = "output",
    ) -> bool:
        """Download a generated image to disk.

        Args:
            filename: Image filename.
            save_path: Local save path.
            subfolder: Subfolder name.
            output_type: Output type.

        Returns:
            True if download succeeded.
        """
        data = self.get_image(filename, subfolder, output_type)
        if data:
            os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(data)
            logger.info(f"ComfyUIClient: Downloaded image → {save_path}")
            return True
        return False

    # ----------------------------------------------------------
    # History
    # ----------------------------------------------------------

    def get_history(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Get execution history for a prompt.

        Args:
            prompt_id: Prompt ID.

        Returns:
            History dict or None.
        """
        try:
            resp = self.session.get(
                f"{self.base_url}/history/{prompt_id}",
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json().get(prompt_id)
        except Exception as e:
            logger.debug(f"ComfyUIClient: History query failed: {e}")
        return None

    def get_recent_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent execution history.

        Args:
            limit: Max entries.

        Returns:
            List of history entries.
        """
        try:
            resp = self.session.get(
                f"{self.base_url}/history",
                timeout=10,
            )
            if resp.status_code == 200:
                data = json.loads(resp.content.lstrip(b'\xef\xbb\xbf').decode('utf-8'))
                # Returns dict keyed by prompt_id
                entries = list(data.values())
                return entries[-limit:]
        except Exception as e:
            logger.debug(f"ComfyUIClient: History list failed: {e}")
        return []


