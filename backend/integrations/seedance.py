"""Seedance 2.0 video generation provider via the Volcengine Ark API.

Seedance 2.0 is ByteDance's image-to-video (I2V) model, accessed through the
Volcengine Ark content generation API. It supports:

- Image-to-video generation from a first frame image.
- Tail-frame linking (尾帧衔接) by providing both a first and last frame,
  constraining the video's start and end visuals.
- Configurable duration (4–15 seconds), resolution (480p / 720p / 1080p),
  and aspect ratio (``9:16`` for short drama).
- Last-frame retrieval for chaining consecutive shots.
- Both a standard and a fast model variant.

The provider follows an asynchronous task pattern:

1. **Create task** — ``POST /api/v3/contents/generations/tasks`` with the
   model ID, prompt, first-frame image (base64 data URI), and parameters.
   Returns a task ``id``.
2. **Poll task** — ``GET /api/v3/contents/generations/tasks/{task_id}`` every
   10 seconds until the status becomes ``succeeded`` or ``failed``, with a
   600-second timeout.
3. **Download** — Fetch the generated video URL and (optionally) the last
   frame URL to local files.

Authentication uses a Bearer token from the ``ARK_API_KEY`` (or
``VOLCENGINE_API_KEY``) environment variable, overridable via the
``api_key`` parameter.

Usage::

    from pathlib import Path
    from backend.integrations.seedance import SeedanceProvider

    provider = SeedanceProvider()
    success, last_frame = await provider.generate_video(
        image_path=Path("shot_01_first_frame.png"),
        output_path=Path("shot_01.mp4"),
        prompt="A young woman turns to face the camera, wind blowing her hair",
        duration=10,
        resolution="1080p",
    )
    if success:
        print(f"Video saved; last frame for next shot at {last_frame}")
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import subprocess
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# API constants
# ═══════════════════════════════════════════════════════════════════════════════

#: Base URL for the Volcengine Ark content generation tasks API.
ARK_TASKS_URL = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"

#: Standard Seedance 2.0 model ID (higher quality, longer generation time).
MODEL_STANDARD = "doubao-seedance-2-0-260128"

#: Fast Seedance 2.0 model ID (lower latency, lower cost).
MODEL_FAST = "doubao-seedance-2-0-fast-260128"

#: Polling interval between task status queries (seconds).
POLL_INTERVAL_SECONDS = 10

#: Maximum total wait time for a single task (seconds).
TIMEOUT_SECONDS = 600

#: Minimum allowed video duration (seconds).
MIN_DURATION = 4

#: Maximum allowed video duration (seconds).
MAX_DURATION = 15

#: Valid resolution options supported by Seedance 2.0.
VALID_RESOLUTIONS = frozenset({"480p", "720p", "1080p"})

#: Default aspect ratio for short-drama / vertical video.
DEFAULT_RATIO = "9:16"

#: HTTP timeout for task creation requests (seconds).
_CREATE_TIMEOUT = 60.0

#: HTTP timeout for task status query requests (seconds).
_QUERY_TIMEOUT = 30.0

#: HTTP timeout for file downloads (seconds).
_DOWNLOAD_TIMEOUT = 300.0

#: MIME-type mapping for common image extensions.
_IMAGE_MIME_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _get_ffmpeg_binary() -> str:
    """Return the FFmpeg binary path, preferring imageio-ffmpeg's bundled binary.

    Falls back to the system ``ffmpeg`` command if imageio-ffmpeg is not
    installed. This mirrors the pattern used in
    :mod:`backend.integrations.localdrama` and :mod:`backend.video.composer`.
    """
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _resolve_api_key(api_key: str | None) -> str | None:
    """Resolve the Volcengine Ark API key.

    Resolution order:

    1. The ``api_key`` parameter (highest priority).
    2. The ``ARK_API_KEY`` environment variable.
    3. The ``VOLCENGINE_API_KEY`` environment variable.

    Returns:
        The resolved API key string, or ``None`` if no key is found.
    """
    if api_key:
        return api_key
    return os.environ.get("ARK_API_KEY") or os.environ.get("VOLCENGINE_API_KEY")


def _encode_image_to_data_uri(image_path: Path) -> str:
    """Read an image file and encode it as a base64 data URI.

    The resulting string is suitable for the ``image_url.url`` field in the
    Ark API request body.

    Args:
        image_path: Path to the image file (PNG, JPEG, WEBP, etc.).

    Returns:
        A data URI string in the format ``"data:{mime};base64,{data}"``.

    Raises:
        FileNotFoundError: If the image file does not exist.
    """
    if not image_path.is_file():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    suffix = image_path.suffix.lower()
    mime = _IMAGE_MIME_TYPES.get(suffix, "image/png")
    raw = image_path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ═══════════════════════════════════════════════════════════════════════════════
# Provider
# ═══════════════════════════════════════════════════════════════════════════════

class SeedanceProvider:
    """Seedance 2.0 video generation provider via the Volcengine Ark API.

    This provider generates short videos from a first-frame image (I2V) with
    optional tail-frame linking via a last-frame image. It always requests
    ``return_last_frame=True`` so that the API returns a downloadable last
    frame; if the API does not provide one, the last frame is extracted from
    the downloaded video using FFmpeg.

    The returned last-frame path enables **tail-frame linking** (尾帧衔接):
    passing it as ``end_image_path`` for the next shot ensures visual
    continuity between consecutive clips.

    Args:
        api_key: Volcengine Ark API key. If ``None``, resolved from the
            ``ARK_API_KEY`` / ``VOLCENGINE_API_KEY`` environment variables.
        base_url: Override for the Ark tasks API base URL (mainly for
            testing).

    Example::

        provider = SeedanceProvider()
        success, last_frame = await provider.generate_video(
            image_path=Path("frame_01.png"),
            output_path=Path("shot_01.mp4"),
            prompt="Camera slowly zooms in on the character's face",
            end_image_path=last_frame_of_previous_shot,
            duration=10,
            resolution="1080p",
        )
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url or ARK_TASKS_URL

    # ── public API ───────────────────────────────────────────────────────

    async def generate_video(
        self,
        image_path: Path,
        output_path: Path,
        prompt: str,
        negative_prompt: str = "",
        end_image_path: Path | None = None,
        duration: int = 10,
        resolution: str = "1080p",
        api_key: str | None = None,
        seed: int = 0,
        fast_mode: bool = False,
    ) -> tuple[bool, Path | None]:
        """Generate a video from a first-frame image using Seedance 2.0.

        Submits an I2V task to the Volcengine Ark API, polls for completion,
        downloads the resulting video, and obtains a last-frame image for
        tail-frame linking.

        Args:
            image_path: Path to the first frame image (PNG/JPEG/WEBP).
            output_path: Destination path for the generated MP4 video.
            prompt: Text prompt describing the desired motion and scene.
            negative_prompt: Negative prompt describing what to avoid in the
                generated video.
            end_image_path: Optional last-frame image for tail-frame linking
                (尾帧衔接). When provided, both the first and last frames are
                sent to the API to constrain the video's start and end.
            duration: Video duration in seconds (4–15).
            resolution: Output resolution — ``"480p"``, ``"720p"``, or
                ``"1080p"``.
            api_key: Volcengine Ark API key. If ``None``, falls back to the
                key passed to the constructor, then to the ``ARK_API_KEY`` /
                ``VOLCENGINE_API_KEY`` environment variables.
            seed: Random seed for reproducibility (0 = random).
            fast_mode: If ``True``, use the fast model variant for lower
                latency at the cost of some quality.

        Returns:
            A tuple ``(success, last_frame_path)``:

            - ``(True, path)`` — video generated successfully; ``path`` points
              to the downloaded or extracted last frame, suitable for passing
              as ``end_image_path`` to the next shot.
            - ``(True, None)`` — video generated successfully, but the last
              frame could not be obtained.
            - ``(False, None)`` — generation failed.
        """
        # ── resolve API key ───────────────────────────────────────────
        key = _resolve_api_key(api_key or self._api_key)
        if not key:
            logger.error(
                "Seedance: no API key found "
                "(set ARK_API_KEY or VOLCENGINE_API_KEY)"
            )
            return False, None

        # ── validate inputs ───────────────────────────────────────────
        if not image_path.is_file():
            logger.error("Seedance: first frame image not found: %s", image_path)
            return False, None

        if not (MIN_DURATION <= duration <= MAX_DURATION):
            logger.error(
                "Seedance: duration %d out of range [%d, %d]",
                duration,
                MIN_DURATION,
                MAX_DURATION,
            )
            return False, None

        if resolution not in VALID_RESOLUTIONS:
            logger.error(
                "Seedance: invalid resolution %r (valid: %s)",
                resolution,
                ", ".join(sorted(VALID_RESOLUTIONS)),
            )
            return False, None

        if end_image_path is not None and not end_image_path.is_file():
            logger.warning(
                "Seedance: end image not found, ignoring tail-frame: %s",
                end_image_path,
            )
            end_image_path = None

        # ── build request body ─────────────────────────────────────────
        model = MODEL_FAST if fast_mode else MODEL_STANDARD

        first_frame_uri = _encode_image_to_data_uri(image_path)

        content: list[dict] = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "role": "first_frame",
                "image_url": {"url": first_frame_uri},
            },
        ]

        if end_image_path is not None:
            last_frame_uri = _encode_image_to_data_uri(end_image_path)
            content.append(
                {
                    "type": "image_url",
                    "role": "last_frame",
                    "image_url": {"url": last_frame_uri},
                }
            )
            logger.info(
                "Seedance: tail-frame linking enabled (first + last frame)"
            )

        body: dict = {
            "model": model,
            "content": content,
            "duration": duration,
            "ratio": DEFAULT_RATIO,
            "resolution": resolution,
            "return_last_frame": True,
        }

        if negative_prompt:
            body["negative_prompt"] = negative_prompt
        if seed:
            body["seed"] = seed

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

        logger.info(
            "Seedance: creating task (model=%s, duration=%ds, resolution=%s, "
            "ratio=%s, fast_mode=%s)",
            model,
            duration,
            resolution,
            DEFAULT_RATIO,
            fast_mode,
        )

        # ── create task ────────────────────────────────────────────────
        try:
            task_id = await self._create_task(headers, body)
        except Exception as exc:
            logger.error("Seedance: failed to create task: %s", exc)
            return False, None

        if not task_id:
            logger.error("Seedance: create task returned an empty ID")
            return False, None

        logger.info("Seedance: task created (id=%s)", task_id)

        # ── poll for completion ─────────────────────────────────────────
        try:
            result = await self._poll_task(headers, task_id)
        except Exception as exc:
            logger.error("Seedance: task polling failed: %s", exc)
            return False, None

        if result is None:
            return False, None

        # ── download video ─────────────────────────────────────────────
        video_url = ""
        content_field = result.get("content")
        if isinstance(content_field, dict):
            video_url = str(content_field.get("video_url", ""))

        if not video_url:
            logger.error(
                "Seedance: task succeeded but no video_url in response: %s",
                result,
            )
            return False, None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await self._download_file(video_url, output_path)
        except Exception as exc:
            logger.error("Seedance: failed to download video: %s", exc)
            return False, None

        if not output_path.is_file() or output_path.stat().st_size == 0:
            logger.error(
                "Seedance: downloaded video is empty or missing: %s",
                output_path,
            )
            return False, None

        logger.info(
            "Seedance: video downloaded to %s (%d bytes)",
            output_path,
            output_path.stat().st_size,
        )

        # ── obtain last frame ──────────────────────────────────────────
        # Since return_last_frame=True was set, prefer the API-provided last
        # frame URL. Fall back to FFmpeg extraction from the downloaded video.
        last_frame_path = output_path.with_name(f"{output_path.stem}_lastframe.png")

        last_frame_url = ""
        last_frame_field = result.get("last_frame")
        if isinstance(last_frame_field, dict):
            last_frame_url = str(last_frame_field.get("url", ""))

        if last_frame_url:
            try:
                await self._download_file(last_frame_url, last_frame_path)
                if last_frame_path.is_file() and last_frame_path.stat().st_size > 0:
                    logger.info(
                        "Seedance: last frame downloaded from API to %s",
                        last_frame_path,
                    )
                    return True, last_frame_path
                logger.warning(
                    "Seedance: API last frame download produced empty file"
                )
            except Exception as exc:
                logger.warning(
                    "Seedance: failed to download API last frame: %s", exc
                )

        # Fall back to FFmpeg extraction from the downloaded video.
        if self._extract_last_frame(output_path, last_frame_path):
            logger.info(
                "Seedance: last frame extracted via FFmpeg to %s",
                last_frame_path,
            )
            return True, last_frame_path

        logger.warning("Seedance: could not obtain last frame")
        return True, None

    # ── internal helpers ────────────────────────────────────────────────

    async def _create_task(
        self,
        headers: dict[str, str],
        body: dict,
    ) -> str:
        """Submit a video generation task to the Ark API.

        Args:
            headers: HTTP headers including the Bearer auth token.
            body: The request payload (model, content, parameters).

        Returns:
            The task ID string.

        Raises:
            RuntimeError: If the API rejects the request or returns no ID.
        """
        async with httpx.AsyncClient(timeout=_CREATE_TIMEOUT) as client:
            response = await client.post(
                self._base_url,
                headers=headers,
                json=body,
            )

        if response.status_code >= 400:
            raise RuntimeError(
                f"Ark API rejected task creation: HTTP {response.status_code} "
                f"— {response.text[:500]}"
            )

        data = response.json()
        task_id = str(data.get("id", ""))
        if not task_id:
            raise RuntimeError(f"Ark API returned no task ID: {data}")
        return task_id

    async def _query_task(
        self,
        headers: dict[str, str],
        task_id: str,
    ) -> dict:
        """Query the status of a video generation task.

        Args:
            headers: HTTP headers including the Bearer auth token.
            task_id: The task ID to query.

        Returns:
            The full task response as a dict.

        Raises:
            RuntimeError: If the API returns an HTTP error status.
        """
        url = f"{self._base_url}/{task_id}"
        async with httpx.AsyncClient(timeout=_QUERY_TIMEOUT) as client:
            response = await client.get(url, headers=headers)

        if response.status_code >= 400:
            raise RuntimeError(
                f"Ark API query failed: HTTP {response.status_code} "
                f"— {response.text[:500]}"
            )

        return response.json()

    async def _poll_task(
        self,
        headers: dict[str, str],
        task_id: str,
    ) -> dict | None:
        """Poll a task until it completes or times out.

        Queries the task status every :data:`POLL_INTERVAL_SECONDS` seconds
        until the status is ``succeeded`` or ``failed``, or until
        :data:`TIMEOUT_SECONDS` seconds have elapsed.

        Args:
            headers: HTTP headers including the Bearer auth token.
            task_id: The task ID to poll.

        Returns:
            The final task response dict on success, or ``None`` on
            failure or timeout.
        """
        start = time.monotonic()
        while time.monotonic() - start < TIMEOUT_SECONDS:
            data = await self._query_task(headers, task_id)
            status = str(data.get("status", "")).lower()

            if status == "succeeded":
                logger.info("Seedance: task %s succeeded", task_id)
                return data

            if status == "failed":
                error_info = data.get("error", {})
                logger.error(
                    "Seedance: task %s failed — %s",
                    task_id,
                    error_info or data,
                )
                return None

            elapsed = int(time.monotonic() - start)
            logger.debug(
                "Seedance: task %s status=%s (%ds elapsed)",
                task_id,
                status or "unknown",
                elapsed,
            )
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        logger.error(
            "Seedance: task %s timed out after %ds",
            task_id,
            TIMEOUT_SECONDS,
        )
        return None

    async def _download_file(
        self,
        url: str,
        destination: Path,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Download a file from a URL to a local path.

        The generated content URLs (video, last frame) are typically served
        from a CDN and do not require authentication headers, but the
        ``headers`` parameter is available for cases where it is needed.

        Args:
            url: The source URL.
            destination: Local file path to write the downloaded content.
            headers: Optional HTTP headers.

        Raises:
            RuntimeError: If the download fails with an HTTP error.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(
            timeout=_DOWNLOAD_TIMEOUT,
            follow_redirects=True,
        ) as client:
            response = await client.get(url, headers=headers)

        if response.status_code >= 400:
            raise RuntimeError(
                f"Download failed: HTTP {response.status_code} for {url}"
            )

        destination.write_bytes(response.content)

    def _extract_last_frame(
        self,
        video_path: Path,
        output_image_path: Path,
    ) -> bool:
        """Extract the last frame of a video using FFmpeg.

        Uses FFmpeg's ``-sseof -1`` to seek to the last second and extract a
        single frame. This mirrors the tail-frame extraction pattern in
        :meth:`backend.integrations.localdrama.CharacterConsistency.link_tail_frame`.

        Args:
            video_path: Path to the source video file.
            output_image_path: Destination path for the extracted PNG frame.

        Returns:
            ``True`` if extraction succeeded, ``False`` otherwise.
        """
        if not video_path.is_file():
            logger.warning(
                "Seedance: cannot extract last frame — video missing: %s",
                video_path,
            )
            return False

        output_image_path.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = _get_ffmpeg_binary()

        cmd = [
            ffmpeg,
            "-sseof", "-1",
            "-i", str(video_path),
            "-update", "1",
            "-q:v", "2",
            "-frames:v", "1",
            "-y",
            str(output_image_path),
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
                    "Seedance: ffmpeg last-frame extraction failed: %s",
                    (result.stderr or "")[-500:],
                )
                return False
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning(
                "Seedance: ffmpeg last-frame extraction error: %s", exc
            )
            return False

        if not output_image_path.is_file() or output_image_path.stat().st_size == 0:
            logger.warning(
                "Seedance: ffmpeg produced no output file: %s",
                output_image_path,
            )
            return False

        return True


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level convenience
# ═══════════════════════════════════════════════════════════════════════════════

def check_availability(api_key: str | None = None) -> bool:
    """Check if the Volcengine Ark API is accessible.

    Resolves the API key (parameter -> ``ARK_API_KEY`` ->
    ``VOLCENGINE_API_KEY``) and attempts a lightweight HTTP request to the
    Ark tasks endpoint. The API is considered accessible when:

    1. An API key can be resolved, **and**
    2. The Ark endpoint responds with any HTTP status (even an error code
       like 401 or 404 confirms the server is reachable).

    Args:
        api_key: Optional API key override.

    Returns:
        ``True`` if the API key is available and the endpoint is reachable,
        ``False`` otherwise.
    """
    key = _resolve_api_key(api_key)
    if not key:
        return False

    headers = {"Authorization": f"Bearer {key}"}
    try:
        with httpx.Client(timeout=10.0) as client:
            client.get(ARK_TASKS_URL, headers=headers)
        # Any HTTP response means the server is reachable.
        return True
    except httpx.HTTPError as exc:
        logger.debug("Seedance: availability check failed: %s", exc)
        return False
    except Exception as exc:
        logger.debug("Seedance: availability check error: %s", exc)
        return False


__all__ = [
    "ARK_TASKS_URL",
    "MODEL_STANDARD",
    "MODEL_FAST",
    "POLL_INTERVAL_SECONDS",
    "TIMEOUT_SECONDS",
    "MIN_DURATION",
    "MAX_DURATION",
    "VALID_RESOLUTIONS",
    "DEFAULT_RATIO",
    "SeedanceProvider",
    "check_availability",
]
