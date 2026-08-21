"""Director providers (Phase 10.7-B)."""

from backend.director.providers.base import DirectorProvider, ProviderError
from backend.director.providers.claude_provider import ClaudeDirectorProvider
from backend.director.providers.openai_provider import OpenAIDirectorProvider
from backend.director.providers.qwen_provider import QwenDirectorProvider
from backend.director.providers.rule_provider import RuleDirectorProvider

__all__ = [
    "DirectorProvider",
    "ProviderError",
    "RuleDirectorProvider",
    "QwenDirectorProvider",
    "OpenAIDirectorProvider",
    "ClaudeDirectorProvider",
]


def default_llm_provider() -> DirectorProvider | None:
    """Auto-detect the best available LLM director (local Qwen first)."""
    qwen = QwenDirectorProvider()
    if qwen.is_available:
        return qwen
    openai = OpenAIDirectorProvider()
    if openai.is_available:
        return openai
    claude = ClaudeDirectorProvider()
    if claude.is_available:
        return claude
    return None
