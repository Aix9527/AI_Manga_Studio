"""MiniMax H3 video generation provider.

This module provides an async client for the MiniMax H3 AI video generation
API, supporting image-to-video (I2V) generation with optional tail-frame
linking (尾帧衔接) for cross-shot visual continuity.

MiniMax H3 is accessed via an asynchronous task-based API:

    1. **Create task** -- ``POST /v2/video_generation`` with a content array
       containing the text prompt and one or two image references (first frame
       and optionally a last frame for tail-frame linking).
    2. **Poll task**    -- ``GET /v2/query/video_generation/{task_id}`` every
       10 seconds until the task reaches a terminal status
       (``succeeded`` or ``failed``) or the 600-second timeout is exceeded.
    3. **Download**     -- fetch the generated MP4 from the URL returned in the
       task response and save it to ``output_path``.
    4. **Extract frame** -- use FFmpeg to extract the last frame of the
       downloaded video, returning its path so the caller can pass it as the
       first frame of the next shot (tail-frame linking).

Key behaviours:

- **I2V ratio**: MiniMax H3 forces the aspect ratio to ``"adaptive"`` for
  image-to-video requests (the output matches the input image dimensions).
  The ``ratio`` parameter is therefore ignored for I2V; see the
  :meth:`MiniMaxH3Provider.generate_video` docstring for details.
- **Base64 data URIs**: input images are encoded as
  ``data:image/png;base64,...`` data URIs before being sent in the content
  array, so no separate image upload step is required.
- **Tail-frame linking**: when ``end_image_path`` is provided, it is sent as
  a ``last_frame`` image in the content array, allowing the model to generate
  a smooth transition between the first and last frames.
- **API key resolution**: the key is resolved from the ``api_key`` parameter,
  falling back to the ``MINIMAX_API_KEY`` environment variable.

References:
- MiniMax H3 API documentation (video generation v2 endpoint)
- :mod:`backend.integrations.localdrama` -- tail-frame linking pattern
"""

from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
import os
import subprocess
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# API constants
# ═══════════════════════════════════════════════════════════════════════════════

#: Base URL for the MiniMax v2 API.
_MINIMAX_BASE_URL = "https://api.minimax.io/v2"

#: Endpoint for creating a video generation task.
_CREATE_TASK_ENDPOINT = f"{_MINIMAX_BASE_URL}/video_generation"

#: Template for querying a video generation task by ID.
_QUERY_TASK_ENDPOINT = f"{_MINIMAX_BASE_URL}/query/video_generation/{{task_id}}"

#: The model identifier used in all requests.
_MODEL = "MiniMax-H3"

#: Interval (seconds) between polling the task status.
_POLL_INTERVAL_SECONDS = 10

#: Maximum total time (seconds) to wait for a task to complete.
_POLL_TIMEOUT_SECONDS = 600

#: Environment variable name holding the MiniMax API key.
_API_KEY_ENV_VAR = "MINIMAX_API_KEY"

# ── Parameter validation ──────────────────────────────────────────────────────

#: Valid duration range (inclusive, in seconds).
_MIN_DURATION = 4
_MAX_DURATION = 15

#: Valid resolution identifiers.
_VALID_RESOLUTIONS = frozenset({"768P", "2K"})

#: Ratio used for short-drama (T2V). I2V forces ``"adaptive"`` instead.
_SHORT_DRAMA_RATIO = "9:16"
_I2V_RATIO = "adaptive"

#: Terminal task statuses -- polling stops once one of these is observed.
_TERMINAL_STATUSES = frozenset({"succeeded", "failed"})

#: HTTP timeout (seconds) for individual API calls (not polling).
_HTTP_TIMEOUT_SECONDS = 30.0

#: HTTP timeout (seconds) for downloading the generated video file.
_DOWNLOAD_TIMEOUT_SECONDS = 120.0


# ═══════════════════════════════════════════════════════════════════════════════
# MiniMaxH3Provider
# ═══════════════════════════════════════════════════════════════════════════════

class MiniMaxH3Provider:
    """Async MiniMax H3 video generation provider.

    Wraps the MiniMax H3 v2 video generation API to produce MP4 videos from
    a first-frame image (I2V).  An optional last-frame image enables
    tail-frame linking (尾帧衔接) so consecutive shots maintain visual
    continuity.

    Usage::

        provider = MiniMaxH3Provider()
        success, last_frame = await provider.generate_video(
            image_path=Path("shot_01_frame.png"),
            output_path=Path("shot_01.mp4"),
            prompt="A girl walks through a rainy street at night",
            duration=10,
        )
        if success:
            # Pass ``last_frame`` as the first frame of the next shot.
            ...

    API key resolution order:

    1. The ``api_key`` parameter passed to :meth:`generate_video`.
    2. The ``api_key`` parameter passed to :meth:`__init__`.
    3. The ``MINIMAX_API_KEY`` environment variable.

    Args:
        api_key: Optional default API key.  If ``None``, the key is read
            from the ``MINIMAX_API_KEY`` environment variable at call time.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    # ── Public API ───────────────────────────────────────────────────────────

    async def generate_video(
        self,
        image_path: Path,
        output_path: Path,
        prompt: str,
        negative_prompt: str = "",
        end_image_path: Path | None = None,
        duration: int = 10,
        resolution: str = "768P",
        api_key: str | None = None,
        seed: int = 0,
    ) -> tuple[bool, Path | None]:
        """Generate a video from a first-frame image via MiniMax H3.

        Sends an I2V request to the MiniMax H3 API, polls until the task
        completes, downloads the resulting MP4, and extracts the last frame
        for tail-frame linking.

        Args:
            image_path: Path to the first-frame image (PNG/JPG).
            output_path: Destination path for the generated MP4 file.
            prompt: Text prompt describing the desired video content.
            negative_prompt: Optional negative prompt (elements to avoid).
                Included as a top-level ``negative_prompt`` field in the
                request body when non-empty.
            end_image_path: Optional path to a last-frame image.  When
                provided, the content array includes a ``last_frame``
                image element for tail-frame linking.
            duration: Video duration in seconds (4-15, inclusive).
            resolution: Target resolution -- ``"768P"`` or ``"2K"``.
            api_key: Override API key.  Falls back to the key passed to
                :meth:`__init__` or the ``MINIMAX_API_KEY`` environment
                variable.
            seed: Random seed for reproducibility.  Included in the request
                body only when non-zero.

        Returns:
            A ``(success, last_frame_path)`` tuple.

            * ``(True, Path)`` -- video generated and last frame extracted.
            * ``(True, None)`` -- video generated but last-frame extraction
              failed (the video itself is still valid).
            * ``(False, None)`` -- generation failed; ``output_path`` should
              not be relied upon.

        Note:
            MiniMax H3 forces the aspect ratio to ``"adaptive"`` for I2V
            requests.  The output dimensions match the input image, so the
            ``ratio`` parameter from the short-drama T2V flow is not
            applicable here.
        """
        # -- Resolve API key -------------------------------------------------
        resolved_key = self._resolve_api_key(api_key)
        if not resolved_key:
            logger.error(
                "MiniMax H3: no API key provided (set %s env var or pass api_key)",
                _API_KEY_ENV_VAR,
            )
            return (False, None)

        # -- Validate inputs -------------------------------------------------
        if not image_path.is_file():
            logger.error("MiniMax H3: first-frame image not found: %s", image_path)
            return (False, None)

        if not (_MIN_DURATION <= duration <= _MAX_DURATION):
            logger.error(
                "MiniMax H3: duration %d out of range [%d, %d]",
                duration,
                _MIN_DURATION,
                _MAX_DURATION,
            )
            return (False, None)

        if resolution not in _VALID_RESOLUTIONS:
            logger.error(
                "MiniMax H3: invalid resolution %r (expected one of %s)",
                resolution,
                sorted(_VALID_RESOLUTIONS),
            )
            return (False, None)

        if end_image_path is not None and not end_image_path.is_file():
            logger.error(
                "MiniMax H3: end-frame image not found: %s", end_image_path
            )
            return (False, None)

        # -- Build request body ----------------------------------------------
        content = self._build_content(
            prompt=prompt,
            negative_prompt=negative_prompt,
            image_path=image_path,
            end_image_path=end_image_path,
        )

        body: dict[str, object] = {
            "model": _MODEL,
            "content": content,
            "resolution": resolution,
            "duration": duration,
            # I2V forces adaptive ratio (output matches input image dims).
            "ratio": _I2V_RATIO,
        }
        if negative_prompt:
            body["negative_prompt"] = negative_prompt
        if seed:
            body["seed"] = seed

        headers = {
            "Authorization": f"Bearer {resolved_key}",
            "Content-Type": "application/json",
        }

        # -- Ensure output directory exists ---------------------------------
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # -- Execute the async generation workflow ---------------------------
        try:
            async with httpx.AsyncClient(
                trust_env=False,
                timeout=_HTTP_TIMEOUT_SECONDS,
            ) as client:
                # Step 1: create the task
                task_id = await self._create_task(client, body, headers)
                if task_id is None:
                    return (False, None)

                # Step 2: poll until completion
                result = await self._poll_task(client, task_id, headers)
                if result is None:
                    return (False, None)

                # Step 3: download the generated video
                video_url = result.get("url")
                if not video_url:
                    logger.error("MiniMax H3: no video URL in task response")
                    return (False, None)

                downloaded = await self._download_video(
                    client, video_url, output_path, resolved_key
                )
                if not downloaded:
                    return (False, None)

                logger.info(
                    "MiniMax H3: video saved to %s (task_id=%s, duration=%ds, "
                    "resolution=%s)",
                    output_path,
                    task_id,
                    duration,
                    resolution,
                )

        except httpx.HTTPError as exc:
            logger.error("MiniMax H3: HTTP error during generation: %s", exc)
            return (False, None)
        except Exception as exc:  # noqa: BLE001 -- catch-all for graceful failure
            logger.error("MiniMax H3: unexpected error: %s", exc, exc_info=True)
            return (False, None)

        # -- Step 4: extract last frame for tail-frame linking ---------------
        last_frame_path = self._extract_last_frame(output_path)
        if last_frame_path is not None:
            logger.info(
                "MiniMax H3: extracted last frame to %s", last_frame_path
            )
        else:
            logger.warning(
                "MiniMax H3: last-frame extraction failed (video is still valid)"
            )

        return (True, last_frame_path)

    # ── Internal helpers ────────────────────────────────────────────────────

    def _resolve_api_key(self, api_key: str | None) -> str:
        """Resolve the API key from the parameter, instance, or environment.

        Resolution order:
        1. The ``api_key`` argument (highest priority).
        2. The key stored on the instance (from :meth:`__init__`).
        3. The ``MINIMAX_API_KEY`` environment variable.

        Returns:
            The resolved key string, or an empty string if none is found.
        """
        if api_key:
            return api_key
        if self._api_key:
            return self._api_key
        return os.environ.get(_API_KEY_ENV_VAR, "")

    @staticmethod
    def _build_content(
        prompt: str,
        negative_prompt: str,
        image_path: Path,
        end_image_path: Path | None,
    ) -> list[dict[str, object]]:
        """Build the MiniMax H3 content array for an I2V request.

        The content array always contains:

        1. A ``text`` element with the prompt.
        2. An ``image_url`` element with ``role: "first_frame"`` for the
           first-frame image.

        When ``end_image_path`` is provided, a third ``image_url`` element
        with ``role: "last_frame"`` is appended for tail-frame linking.

        Args:
            prompt: The text prompt.
            negative_prompt: Unused in the content array (sent as a
                top-level field instead).  Accepted for signature symmetry.
            image_path: Path to the first-frame image.
            end_image_path: Optional path to the last-frame image.

        Returns:
            The content list ready for inclusion in the request body.
        """
        # ``negative_prompt`` is intentionally not embedded in the text
        # element; it is sent as a top-level request field instead.
        _ = negative_prompt

        content: list[dict[str, object]] = [
            {
                "type": "text",
                "text": prompt,
            },
        ]

        # First frame (always present for I2V)
        first_frame_uri = MiniMaxH3Provider._encode_image_to_data_uri(image_path)
        content.append(
            {
                "type": "image_url",
                "role": "first_frame",
                "image_url": {"url": first_frame_uri},
            }
        )

        # Last frame (optional -- enables tail-frame linking)
        if end_image_path is not None:
            last_frame_uri = MiniMaxH3Provider._encode_image_to_data_uri(
                end_image_path
            )
            content.append(
                {
                    "type": "image_url",
                    "role": "last_frame",
                    "image_url": {"url": last_frame_uri},
                }
            )

        return content

    @staticmethod
    def _encode_image_to_data_uri(image_path: Path) -> str:
        """Encode an image file as a base64 data URI.

        Determines the MIME type from the file extension (defaulting to
        ``image/png``) and returns a string of the form::

            data:image/png;base64,<base64-encoded-bytes>

        Args:
            image_path: Path to the image file.

        Returns:
            The base64 data URI string.
        """
        mime_type, _ = mimetypes.guess_type(str(image_path))
        if not mime_type or not mime_type.startswith("image/"):
            mime_type = "image/png"

        raw_bytes = image_path.read_bytes()
        b64_data = base64.b64encode(raw_bytes).decode("ascii")
        return f"data:{mime_type};base64,{b64_data}"

    @staticmethod
    async def _create_task(
        client: httpx.AsyncClient,
        body: dict[str, object],
        headers: dict[str, str],
    ) -> str | None:
        """Send the create-task request and return the task ID.

        Args:
            client: The async HTTP client.
            body: The request body dict.
            headers: The request headers (auth + content-type).

        Returns:
            The task ID string, or ``None`` if the request failed.
        """
        try:
            resp = await client.post(
                _CREATE_TASK_ENDPOINT,
                json=body,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            logger.error("MiniMax H3: create-task request failed: %s", exc)
            return None

        if resp.status_code != 200:
            logger.error(
                "MiniMax H3: create-task returned HTTP %d: %s",
                resp.status_code,
                (resp.text or "")[:500],
            )
            return None

        try:
            data = resp.json()
        except ValueError:
            logger.error("MiniMax H3: create-task returned non-JSON response")
            return None

        task_id = data.get("task_id")
        if not task_id:
            logger.error(
                "MiniMax H3: create-task response missing task_id: %s",
                str(data)[:500],
            )
            return None

        logger.info("MiniMax H3: task created (task_id=%s)", task_id)
        return str(task_id)

    @staticmethod
    async def _poll_task(
        client: httpx.AsyncClient,
        task_id: str,
        headers: dict[str, str],
    ) -> dict[str, object] | None:
        """Poll the task status until it reaches a terminal state.

        Polls every ``_POLL_INTERVAL_SECONDS`` seconds, up to
        ``_POLL_TIMEOUT_SECONDS`` seconds total.  Returns the task's
        ``content`` dict (containing the video URL) on success.

        Args:
            client: The async HTTP client.
            task_id: The task ID to query.
            headers: The request headers.

        Returns:
            The ``content`` dict from the task response on success, or
            ``None`` if the task failed or timed out.
        """
        query_url = _QUERY_TASK_ENDPOINT.format(task_id=task_id)
        elapsed = 0

        while elapsed < _POLL_TIMEOUT_SECONDS:
            try:
                resp = await client.get(query_url, headers=headers)
            except httpx.HTTPError as exc:
                logger.warning("MiniMax H3: poll request failed: %s", exc)
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)
                elapsed += _POLL_INTERVAL_SECONDS
                continue

            if resp.status_code != 200:
                logger.warning(
                    "MiniMax H3: poll returned HTTP %d: %s",
                    resp.status_code,
                    (resp.text or "")[:300],
                )
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)
                elapsed += _POLL_INTERVAL_SECONDS
                continue

            try:
                data = resp.json()
            except ValueError:
                logger.warning("MiniMax H3: poll returned non-JSON response")
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)
                elapsed += _POLL_INTERVAL_SECONDS
                continue

            task = data.get("task", {})
            status = str(task.get("status", "")).lower()

            logger.debug(
                "MiniMax H3: task %s status=%s (elapsed=%ds)",
                task_id,
                status,
                elapsed,
            )

            if status == "succeeded":
                content = task.get("content")
                if isinstance(content, dict):
                    usage = task.get("usage")
                    if usage:
                        logger.info(
                            "MiniMax H3: task %s succeeded (usage=%s)",
                            task_id,
                            usage,
                        )
                    else:
                        logger.info("MiniMax H3: task %s succeeded", task_id)
                    return content
                logger.error(
                    "MiniMax H3: task %s succeeded but content is missing or "
                    "not a dict: %s",
                    task_id,
                    str(content)[:300],
                )
                return None

            if status == "failed":
                logger.error(
                    "MiniMax H3: task %s failed: %s",
                    task_id,
                    str(task.get("base_resp", task))[:500],
                )
                return None

            # Still queued or running -- wait and retry.
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS

        logger.error(
            "MiniMax H3: task %s timed out after %ds",
            task_id,
            _POLL_TIMEOUT_SECONDS,
        )
        return None

    @staticmethod
    async def _download_video(
        client: httpx.AsyncClient,
        video_url: str,
        output_path: Path,
        api_key: str,
    ) -> bool:
        """Download the generated video and save it to ``output_path``.

        Streams the response body to disk to handle large video files
        without loading the entire file into memory.

        Args:
            client: The async HTTP client.
            video_url: The URL of the generated MP4.
            output_path: Destination file path.
            api_key: API key (included as a bearer token in case the
                download URL requires authentication).

        Returns:
            ``True`` if the download succeeded, ``False`` otherwise.
        """
        download_headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with client.stream(
                "GET",
                video_url,
                headers=download_headers,
                timeout=_DOWNLOAD_TIMEOUT_SECONDS,
            ) as resp:
                if resp.status_code != 200:
                    logger.error(
                        "MiniMax H3: video download returned HTTP %d",
                        resp.status_code,
                    )
                    return False

                with open(output_path, "wb") as f:
                    async for chunk in resp.aiter_bytes():
                        f.write(chunk)
        except httpx.HTTPError as exc:
            logger.error("MiniMax H3: video download failed: %s", exc)
            return False

        if not output_path.is_file() or output_path.stat().st_size == 0:
            logger.error(
                "MiniMax H3: downloaded video is empty or missing: %s",
                output_path,
            )
            return False

        return True

    @staticmethod
    def _extract_last_frame(video_path: Path) -> Path | None:
        """Extract a tail frame for linking (GPT P2: quality-scored handoff).

        Tries :func:`select_handoff_frame` first (best-scoring frame from the
        last N frames, avoiding the blurriest last frame). Falls back to the
        classic ``-sseof -1`` extraction when handoff selection fails.
        Returns a PNG at ``{stem}_lastframe.png``.
        """
        if not video_path.exists():
            logger.warning(
                "MiniMax H3: cannot extract last frame -- video not found: %s",
                video_path,
            )
            return None

        last_frame_path = video_path.parent / f"{video_path.stem}_lastframe.png"
        last_frame_path.parent.mkdir(parents=True, exist_ok=True)

        # GPT P2: 先尝试质量评分 Handoff（避免机械取最后一帧）
        try:
            from backend.video.tailframe import select_handoff_frame
            handoff_dir = video_path.parent / "handoff"
            handoff_dir.mkdir(parents=True, exist_ok=True)
            best = select_handoff_frame(video_path, handoff_dir)
            if best is not None:
                import shutil
                shutil.copy2(best, last_frame_path)
                logger.info(
                    "MiniMax H3: handoff frame %s -> %s",
                    best.name, last_frame_path.name,
                )
                return last_frame_path
        except Exception as exc:  # noqa: BLE001
            logger.debug("MiniMax H3: handoff selector failed, fallback: %s", exc)

        ffmpeg = _get_ffmpeg_binary()

        cmd = [
            ffmpeg,
            "-sseof", "-1",
            "-i", str(video_path),
            "-update", "1",
            "-q:v", "2",
            "-frames:v", "1",
            "-y",
            str(last_frame_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.warning(
                    "MiniMax H3: ffmpeg last-frame extraction failed: %s",
                    (result.stderr or "")[-500:],
                )
                return None
        except FileNotFoundError as exc:
            logger.warning("MiniMax H3: ffmpeg binary not found: %s", exc)
            return None
        except subprocess.TimeoutExpired:
            logger.warning("MiniMax H3: ffmpeg last-frame extraction timed out")
            return None

        if not last_frame_path.exists():
            logger.warning(
                "MiniMax H3: last-frame output not created: %s", last_frame_path
            )
            return None

        return last_frame_path


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level utilities
# ═══════════════════════════════════════════════════════════════════════════════

def _get_ffmpeg_binary() -> str:
    """Return the FFmpeg binary path, preferring imageio-ffmpeg's bundled binary.

    Falls back to the system ``ffmpeg`` command if imageio-ffmpeg is not
    installed.  This mirrors the pattern in
    :mod:`backend.integrations.localdrama`.
    """
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def check_availability(api_key: str | None = None) -> bool:
    """Check if the MiniMax H3 API is accessible.

    Performs a lightweight reachability check:

    1. Verifies that an API key is available (from the parameter or the
       ``MINIMAX_API_KEY`` environment variable).
    2. Attempts an HTTP connection to the MiniMax API endpoint.

    Any HTTP response (including error status codes such as 401 or 400)
    indicates the API is reachable -- the check only returns ``False`` when
    the endpoint cannot be contacted at all (network error, DNS failure,
    etc.) or no API key is configured.

    Args:
        api_key: Optional API key override.  Falls back to the
            ``MINIMAX_API_KEY`` environment variable.

    Returns:
        ``True`` if the API key is present and the endpoint is reachable,
        ``False`` otherwise.
    """
    resolved_key = api_key or os.environ.get(_API_KEY_ENV_VAR, "")
    if not resolved_key:
        logger.debug(
            "MiniMax H3: availability check failed -- no API key (set %s)",
            _API_KEY_ENV_VAR,
        )
        return False

    headers = {
        "Authorization": f"Bearer {resolved_key}",
        "Content-Type": "application/json",
    }

    # Send a minimal create-task request.  A structured error response
    # (HTTP 4xx) means the API is reachable and responding; only a
    # connection-level failure indicates the API is down.
    probe_body = {
        "model": _MODEL,
        "content": [{"type": "text", "text": ""}],
        "resolution": "768P",
        "duration": _MIN_DURATION,
        "ratio": _I2V_RATIO,
    }

    try:
        with httpx.Client(trust_env=False, timeout=10.0) as client:
            resp = client.post(_CREATE_TASK_ENDPOINT, json=probe_body, headers=headers)
            # Any HTTP response means the API endpoint is reachable.
            # A 4xx error (e.g. 400 for empty prompt, 401 for bad key) still
            # confirms network connectivity to the API.
            return resp.status_code is not None
    except httpx.HTTPError as exc:
        logger.debug("MiniMax H3: availability check failed: %s", exc)
        return False
    except Exception as exc:  # noqa: BLE001 -- catch-all for graceful failure
        logger.debug("MiniMax H3: availability check error: %s", exc)
        return False
