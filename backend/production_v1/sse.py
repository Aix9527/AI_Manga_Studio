"""Production SSE 实时广播（Agent Runtime 实时化）.

生产状态变更 → asyncio.Queue 广播 → /api/production/events SSE 流。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncGenerator


class ProductionSSE:
    """SSE 广播管理器：订阅者队列 + 广播状态。"""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> AsyncGenerator[str, None]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        async with self._lock:
            self._subscribers.add(queue)
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    async def broadcast(self, event: dict) -> None:
        payload = json.dumps(event, ensure_ascii=False)
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(payload)
                except Exception:  # noqa: BLE001
                    pass


sse = ProductionSSE()


async def broadcast_status(project_id: str, status: dict) -> None:
    await sse.broadcast({"type": "production_status", "project_id": project_id, "status": status})
