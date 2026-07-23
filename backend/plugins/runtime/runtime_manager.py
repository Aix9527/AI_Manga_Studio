"""
Runtime Manager — Plugin execution isolation (Part 18)

Manages three runtime modes for plugins:
- in_process: Direct Python import (fast, no isolation)
- subprocess: Separate process with IPC (default for production)
- remote: Network-based RPC (for external plugin services)
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RuntimeType(str, Enum):
    IN_PROCESS = "in_process"
    SUBPROCESS = "subprocess"
    REMOTE = "remote"


@dataclass
class RuntimeConfig:
    """Configuration for a plugin runtime."""
    runtime_type: RuntimeType = RuntimeType.IN_PROCESS
    entrypoint: str = ""  # module:function
    timeout_seconds: float = 30.0
    max_restarts: int = 3
    env: dict[str, str] = field(default_factory=dict)
    args: list[str] = field(default_factory=list)


class RuntimeManager:
    """Manages plugin runtimes — starts, stops, and monitors plugins."""

    def __init__(self) -> None:
        self._runtimes: dict[str, RuntimeConfig] = {}
        self._processes: dict[str, asyncio.subprocess.Process | None] = {}
        self._instances: dict[str, Any] = {}  # in-process instances

    def register(self, plugin_id: str, config: RuntimeConfig) -> None:
        self._runtimes[plugin_id] = config

    async def start(self, plugin_id: str) -> Any | None:
        """Start a plugin and return its instance or None."""
        config = self._runtimes.get(plugin_id)
        if not config:
            logger.error(f"No runtime config for plugin '{plugin_id}'")
            return None

        if config.runtime_type == RuntimeType.IN_PROCESS:
            return await self._start_in_process(plugin_id, config)
        elif config.runtime_type == RuntimeType.SUBPROCESS:
            return await self._start_subprocess(plugin_id, config)
        elif config.runtime_type == RuntimeType.REMOTE:
            return await self._start_remote(plugin_id, config)
        return None

    async def stop(self, plugin_id: str) -> None:
        """Stop a plugin runtime."""
        if plugin_id in self._instances:
            instance = self._instances.pop(plugin_id)
            if hasattr(instance, "shutdown"):
                if asyncio.iscoroutinefunction(instance.shutdown):
                    await instance.shutdown()
                else:
                    instance.shutdown()

        if plugin_id in self._processes:
            proc = self._processes.pop(plugin_id)
            if proc:
                proc.terminate()
                await proc.wait()

    async def _start_in_process(self, plugin_id: str, config: RuntimeConfig) -> Any | None:
        """Load plugin via dynamic import."""
        try:
            module_name, func_name = config.entrypoint.split(":", 1)
            module = importlib.import_module(module_name)
            factory = getattr(module, func_name)
            instance = factory()
            self._instances[plugin_id] = instance
            logger.info(f"Plugin '{plugin_id}' loaded in-process")
            return instance
        except Exception as e:
            logger.error(f"Failed to load plugin '{plugin_id}' in-process: {e}")
            return None

    async def _start_subprocess(self, plugin_id: str, config: RuntimeConfig) -> Any | None:
        """Start plugin as a subprocess with IPC."""
        # Subprocess communication via stdin/stdout JSON-RPC
        try:
            proc = await asyncio.create_subprocess_exec(
                "python", "-m", config.entrypoint.replace(":", "."),
                *config.args,
                env={**__import__("os").environ, **config.env},
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._processes[plugin_id] = proc
            logger.info(f"Plugin '{plugin_id}' started as subprocess (PID: {proc.pid})")
            return proc  # Return process handle for IPC
        except Exception as e:
            logger.error(f"Failed to start plugin '{plugin_id}' subprocess: {e}")
            return None

    async def _start_remote(self, plugin_id: str, config: RuntimeConfig) -> Any | None:
        """Connect to remote plugin service."""
        logger.info(f"Plugin '{plugin_id}' configured for remote runtime (not yet connected)")
        return None

    def get_instance(self, plugin_id: str) -> Any | None:
        """Get the running instance of an in-process plugin."""
        return self._instances.get(plugin_id)

    def list_running(self) -> list[str]:
        return list(self._instances.keys()) + list(self._processes.keys())
