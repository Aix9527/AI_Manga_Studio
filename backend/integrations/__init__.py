"""
Integrations — MCP, A2A, and External Services (Part 25)

Provides integration points:
- MCP Server: Expose AI_Manga_Studio as an MCP server
- MCP Client: Connect to external MCP servers
- A2A Protocol: Agent-to-agent communication
- External API adapters
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

import logging
logger = logging.getLogger(__name__)


# ── MCP Protocol ──────────────────────────────────────────────────────

class MCPRole(str, Enum):
    SERVER = "server"
    CLIENT = "client"


@dataclass
class MCPTool:
    """An MCP tool definition."""
    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.parameters,
        }


@dataclass
class MCPResource:
    """An MCP resource definition."""
    uri: str
    name: str = ""
    description: str = ""
    mime_type: str = "application/json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


class MCPServer:
    """MCP Server that exposes AI_Manga_Studio capabilities."""

    def __init__(self, name: str = "ai_manga_studio", version: str = "0.9.0") -> None:
        self._name = name
        self._version = version
        self._tools: dict[str, MCPTool] = {}
        self._tool_handlers: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}
        self._resources: dict[str, MCPResource] = {}

    def register_tool(
        self,
        tool: MCPTool,
        handler: Callable[..., Coroutine[Any, Any, Any]],
    ) -> None:
        """Register an MCP tool."""
        self._tools[tool.name] = tool
        self._tool_handlers[tool.name] = handler

    def register_resource(self, resource: MCPResource) -> None:
        """Register an MCP resource."""
        self._resources[resource.uri] = resource

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Execute a registered MCP tool."""
        handler = self._tool_handlers.get(tool_name)
        if not handler:
            raise ValueError(f"Unknown tool: {tool_name}")
        return await handler(**arguments)

    def list_tools(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self._tools.values()]

    def list_resources(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._resources.values()]


class MCPClient:
    """MCP Client to connect to external MCP servers."""

    def __init__(self, server_url: str) -> None:
        self._server_url = server_url

    async def list_tools(self) -> list[dict[str, Any]]:
        """Fetch available tools from the MCP server."""
        return []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on the MCP server."""
        return {}


# ── A2A Protocol ──────────────────────────────────────────────────────

class A2AMessage:
    """Agent-to-Agent communication message."""

    def __init__(
        self,
        sender_agent: str,
        receiver_agent: str,
        message_type: str,
        payload: dict[str, Any],
        correlation_id: str = "",
    ) -> None:
        self.sender_agent = sender_agent
        self.receiver_agent = receiver_agent
        self.message_type = message_type
        self.payload = payload
        self.correlation_id = correlation_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "sender": self.sender_agent,
            "receiver": self.receiver_agent,
            "type": self.message_type,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
        }


class A2ABroker:
    """Agent-to-Agent message broker."""

    def __init__(self) -> None:
        self._agents: dict[str, Any] = {}  # agent_name -> agent instance
        self._message_handlers: dict[str, list[Callable]] = {}

    def register_agent(self, name: str, agent: Any) -> None:
        self._agents[name] = agent

    def subscribe(self, message_type: str, handler: Callable) -> None:
        if message_type not in self._message_handlers:
            self._message_handlers[message_type] = []
        self._message_handlers[message_type].append(handler)

    async def send(self, message: A2AMessage) -> None:
        """Route a message to the receiver agent."""
        receiver = self._agents.get(message.receiver_agent)
        handlers = self._message_handlers.get(message.message_type, [])

        for handler in handlers:
            await handler(message.to_dict())

        if receiver and hasattr(receiver, "receive_message"):
            await receiver.receive_message(message)


# ── External API Integration ──────────────────────────────────────────

class ExternalAPIClient(ABC):
    """Abstract external API client."""

    @abstractmethod
    async def call(self, endpoint: str, method: str = "GET", data: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class ComfyUIClient(ExternalAPIClient):
    """ComfyUI API client for image/video generation."""

    def __init__(self, base_url: str = "http://localhost:8188") -> None:
        self._base_url = base_url.rstrip("/")

    async def call(self, endpoint: str, method: str = "GET", data: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"status": "ok"}

    async def health_check(self) -> bool:
        return True

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        """Queue a ComfyUI workflow. Returns prompt_id."""
        return "prompt-000"


class LLMClient(ExternalAPIClient):
    """OpenAI-compatible LLM API client."""

    def __init__(self, base_url: str = "http://localhost:11434/v1", api_key: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def call(self, endpoint: str, method: str = "GET", data: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"choices": [{"message": {"content": "Test response"}}]}

    async def health_check(self) -> bool:
        return True

    async def chat(self, messages: list[dict[str, str]], model: str = "qwen3") -> str:
        """Send a chat completion request."""
        result = await self.call("/chat/completions", "POST", {
            "model": model,
            "messages": messages,
        })
        return result.get("choices", [{}])[0].get("message", {}).get("content", "")


# ── Integration Registry ──────────────────────────────────────────────

class IntegrationRegistry:
    """Central registry for all external integrations."""

    def __init__(self) -> None:
        self._mcp_server: MCPServer | None = None
        self._mcp_clients: dict[str, MCPClient] = {}
        self._a2a_broker: A2ABroker | None = None
        self._external_clients: dict[str, ExternalAPIClient] = {}

    def register_mcp_server(self, server: MCPServer) -> None:
        self._mcp_server = server

    def register_mcp_client(self, name: str, client: MCPClient) -> None:
        self._mcp_clients[name] = client

    def register_a2a_broker(self, broker: A2ABroker) -> None:
        self._a2a_broker = broker

    def register_external_client(self, name: str, client: ExternalAPIClient) -> None:
        self._external_clients[name] = client

    def get_external_client(self, name: str) -> ExternalAPIClient | None:
        return self._external_clients.get(name)


# Global integration registry
integration_registry = IntegrationRegistry()
