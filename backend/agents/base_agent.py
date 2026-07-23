"""
Agent Base Class & Core Abstractions (Part 9)

Defines the foundational interfaces and models for all AI Agents
in the Manga Studio pipeline: Story, Character, Scene, Prompt,
Video, Voice, and Director agents.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, AsyncIterator, Generic, Optional, TypeVar
from uuid import uuid4
import time


# ── Result & Context Models ──────────────────────────────────────────────


class AgentStatus(Enum):
    """Execution lifecycle status of an agent invocation."""
    IDLE = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()
    RETRYING = auto()


@dataclass
class AgentResult:
    """Structured output from any agent execution."""
    agent_id: str
    agent_type: str
    status: AgentStatus
    output: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)  # file paths
    tokens_used: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None
    attempt: int = 1
    trace_id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def success(self) -> bool:
        return self.status == AgentStatus.COMPLETED


@dataclass
class AgentContext:
    """Execution context passed through the agent pipeline."""
    project_id: str
    job_id: str
    workflow_run_id: str
    variables: dict[str, Any] = field(default_factory=dict)
    upstream_outputs: dict[str, AgentResult] = field(default_factory=dict)
    memory_snapshot_id: Optional[str] = None
    trace_id: str = field(default_factory=lambda: str(uuid4()))


# ── Base Agent Interface ─────────────────────────────────────────────────

T = TypeVar("T", bound=AgentResult)


class BaseAgent(ABC, Generic[T]):
    """
    Abstract base for all AI Manga Studio agents.

    Every agent declares:
    - Input/output schemas for type safety
    - A set of capabilities it provides
    - Version for tracking and compatibility

    Subclasses implement `_execute_impl()` with domain-specific logic.
    """

    agent_id: str
    agent_type: str
    version: str = "1.0.0"
    capabilities: list[str] = field(default_factory=list)

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        version: str = "1.0.0",
    ) -> None:
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.version = version

    # ── Public API ────────────────────────────────────────

    async def execute(
        self,
        context: AgentContext,
        **kwargs: Any,
    ) -> T:
        """
        Execute this agent with given context and parameters.

        Handles pre/post hooks, timing, error categorization,
        and delegates to `_execute_impl`.
        """
        start = time.perf_counter()
        try:
            result = await self._execute_impl(context, **kwargs)
            result.agent_id = self.agent_id
            result.agent_type = self.agent_type
            result.status = AgentStatus.COMPLETED
        except asyncio.CancelledError:
            return self._error_result(
                "Cancelled", AgentStatus.CANCELLED
            )
        except Exception as exc:
            result = self._error_result(str(exc), AgentStatus.FAILED)
        finally:
            result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    @abstractmethod
    async def _execute_impl(
        self, context: AgentContext, **kwargs: Any
    ) -> T:
        """Domain-specific execution logic. Must be overridden."""
        ...

    async def stream(
        self, context: AgentContext, **kwargs: Any
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream partial results (SSE). Override for streaming agents.
        """
        result = await self.execute(context, **kwargs)
        yield {"status": result.status.name, "output": result.output}

    # ── Schema ─────────────────────────────────────────────

    @classmethod
    def input_schema(cls) -> dict[str, Any]:
        """JSON Schema for agent input parameters."""
        return {}

    @classmethod
    def output_schema(cls) -> dict[str, Any]:
        """JSON Schema for agent result output."""
        return {}

    # ── Capability ─────────────────────────────────────────

    @classmethod
    def declared_capabilities(cls) -> list[str]:
        """List of capability identifiers this agent provides."""
        return []

    # ── Helpers ────────────────────────────────────────────

    def _error_result(
        self, message: str, status: AgentStatus
    ) -> T:
        return AgentResult(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            status=status,
            error=message,
        )  # type: ignore[return-value]


# ── Agent Registry ───────────────────────────────────────────────────────


class AgentRegistry:
    """
    Central registry of all available agents.

    Supports discovery, capability-based lookup, composable agent
    chains, and version pinning.
    """

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}
        self._by_type: dict[str, list[BaseAgent]] = {}
        self._by_capability: dict[str, list[BaseAgent]] = {}

    async def discover(self) -> None:
        """Auto-discover and register all agents from modules."""
        # Registration is done by each module's init.
        pass

    def register(self, agent: BaseAgent) -> None:
        """Register an agent instance."""
        self._agents[agent.agent_id] = agent
        self._by_type.setdefault(agent.agent_type, []).append(agent)
        for cap in agent.declared_capabilities():
            self._by_capability.setdefault(cap, []).append(agent)

    def get(self, agent_id: str) -> Optional[BaseAgent]:
        """Lookup an agent by ID."""
        return self._agents.get(agent_id)

    def find_by_capability(self, capability: str) -> list[BaseAgent]:
        """Find all agents that declare a given capability."""
        return self._by_capability.get(capability, [])

    def find_by_type(self, agent_type: str) -> list[BaseAgent]:
        """Find all agents of a specific type."""
        return self._by_type.get(agent_type, [])

    def list_all(self) -> list[BaseAgent]:
        """List all registered agents."""
        return list(self._agents.values())

    @property
    def count(self) -> int:
        return len(self._agents)
