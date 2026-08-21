from __future__ import annotations

import asyncio
import json
import logging
from urllib.request import urlopen

from backend.novel_video.models import RunStatus
from backend.novel_video.repository import NovelVideoRepository


logger = logging.getLogger(__name__)


RECONCILIATION_ACTIVE_STATUSES = frozenset(
    {
        RunStatus.PLANNING,
        RunStatus.RENDERING,
        RunStatus.MIXING,
        RunStatus.VALIDATING,
    }
)


class RunReconciler:
    def __init__(
        self,
        repository: NovelVideoRepository,
        active_prompt_ids: set[str],
        active_lease_ids: set[str],
        *,
        prompt_query_succeeded: bool = True,
        preserved_run_ids: set[str] | None = None,
    ) -> None:
        self.repository = repository
        self.active_prompt_ids = active_prompt_ids
        self.active_lease_ids = active_lease_ids
        self.prompt_query_succeeded = prompt_query_succeeded
        self.preserved_run_ids = preserved_run_ids or set()

    def reconcile(self) -> list[str]:
        changed: list[str] = []
        for run in self.repository.list_runs():
            if run.status not in RECONCILIATION_ACTIVE_STATUSES:
                continue
            if run.id in self.preserved_run_ids:
                continue
            if run.lease_id and run.lease_id in self.active_lease_ids:
                continue
            if run.comfy_prompt_id:
                if not self.prompt_query_succeeded:
                    logger.warning(
                        "ComfyUI queue state is unknown; preserving prompted run %s",
                        run.id,
                    )
                    continue
                if run.comfy_prompt_id in self.active_prompt_ids:
                    continue
            self.repository.update_run_status(run.id, RunStatus.INTERRUPTED)
            changed.append(run.id)
        return changed


async def fetch_active_comfy_prompt_ids(
    base_url: str = "http://127.0.0.1:8188",
) -> tuple[set[str], bool]:
    return await asyncio.to_thread(_fetch_active_comfy_prompt_ids, base_url)


def _fetch_active_comfy_prompt_ids(base_url: str) -> tuple[set[str], bool]:
    try:
        with urlopen(f"{base_url.rstrip('/')}/queue", timeout=2) as response:
            payload = json.load(response)
        if not isinstance(payload, dict):
            logger.warning("ComfyUI queue query returned an unknown response shape")
            return set(), False
        prompt_ids = _queue_prompt_ids(payload)
        if prompt_ids is None:
            logger.warning("ComfyUI queue query returned malformed queue state")
            return set(), False
        return prompt_ids, True
    except Exception as exc:
        logger.warning("ComfyUI queue query failed; queue state is unknown: %s", exc)
        return set(), False


def _queue_prompt_ids(payload: dict[str, object]) -> set[str] | None:
    prompt_ids: set[str] = set()
    for queue_name in ("queue_running", "queue_pending"):
        entries = payload.get(queue_name)
        if not isinstance(entries, list):
            return None
        for entry in entries:
            prompt_id = _queue_entry_prompt_id(entry)
            if prompt_id is None:
                return None
            prompt_ids.add(prompt_id)
    return prompt_ids


def _queue_entry_prompt_id(entry: object) -> str | None:
    if isinstance(entry, (list, tuple)) and len(entry) > 1:
        prompt_id = entry[1]
        return prompt_id if isinstance(prompt_id, str) and prompt_id else None
    return None
