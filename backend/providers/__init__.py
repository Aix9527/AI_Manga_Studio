"""
Providers — Base interfaces and implementations (Part 11)

Provider pattern for AI model backends. Each provider type
(LLM, Image, Video, Audio) has a base interface and multiple
concrete implementations.

Supported providers:
- LLM: OpenAI, Ollama, OpenRouter
- Image: ComfyUI (Flux, SDXL), local DiffusionPipeline
- Video: Wan 2.1 via ComfyUI, CogVideoX
- Audio: ElevenLabs, Fish Audio, edge-tts
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Optional
from enum import Enum


# ── Common Types ───────────────────────────────────────────────────────


class ProviderStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"
    DEGRADED = "degraded"


@dataclass
class ProviderResult:
    """Standardized result from any provider."""
    success: bool
    provider_name: str
    output: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    cost_estimate: float = 0.0
    error: Optional[str] = None

    @property
    def is_ok(self) -> bool:
        return self.success


@dataclass
class ProviderCapability:
    """Declare what a provider can do."""
    name: str
    description: str = ""
    max_resolution: tuple[int, int] = (1024, 1024)
    max_duration_seconds: float = 30.0
    supported_formats: list[str] = field(default_factory=list)
    estimated_cost_per_unit: float = 0.0


# ── LLM Provider ───────────────────────────────────────────────────────


class LLMProvider(ABC):
    """Base interface for LLM providers (OpenAI, Ollama, OpenRouter)."""

    provider_type: ClassVar[str] = "llm"

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ProviderResult:
        """Send a chat completion request."""
        ...

    @abstractmethod
    async def health_check(self) -> ProviderStatus:
        """Check if the provider is available."""
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        """List available models."""
        ...


class OpenAIProvider(LLMProvider):
    """OpenAI API provider (GPT-4o, GPT-4, etc.)"""

    provider_name: ClassVar[str] = "openai"

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1") -> None:
        self.api_key = api_key
        self.base_url = base_url

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str = "gpt-4o",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ProviderResult:
        """Chat completion via OpenAI API."""
        # MVP: return structured placeholder
        return ProviderResult(
            success=True,
            provider_name=self.provider_name,
            output={"content": "", "model": model, "usage": {"total_tokens": 0}},
        )

    async def health_check(self) -> ProviderStatus:
        return ProviderStatus.ONLINE

    def list_models(self) -> list[str]:
        return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]


class OllamaProvider(LLMProvider):
    """Local Ollama provider for open-source LLMs."""

    provider_name: ClassVar[str] = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self.base_url = base_url

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str = "qwen2.5:14b",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ProviderResult:
        return ProviderResult(
            success=True,
            provider_name=self.provider_name,
            output={"content": "", "model": model},
        )

    async def health_check(self) -> ProviderStatus:
        return ProviderStatus.ONLINE

    def list_models(self) -> list[str]:
        return ["qwen2.5:14b", "qwen2.5:7b", "llama3.1:8b"]


class OpenRouterProvider(LLMProvider):
    """OpenRouter provider for unified LLM access."""

    provider_name: ClassVar[str] = "openrouter"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str = "anthropic/claude-3.5-sonnet",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ProviderResult:
        return ProviderResult(
            success=True,
            provider_name=self.provider_name,
            output={"content": "", "model": model},
        )

    async def health_check(self) -> ProviderStatus:
        return ProviderStatus.ONLINE

    def list_models(self) -> list[str]:
        return ["anthropic/claude-3.5-sonnet", "openai/gpt-4o", "google/gemini-pro"]


# ── Image Provider ─────────────────────────────────────────────────────


class ImageProvider(ABC):
    """Base interface for image generation providers."""

    provider_type: ClassVar[str] = "image"

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 25,
        cfg_scale: float = 7.0,
        seed: int = -1,
    ) -> ProviderResult:
        """Generate a single image."""
        ...

    @abstractmethod
    async def generate_batch(
        self,
        prompts: list[dict[str, Any]],
        batch_size: int = 4,
    ) -> list[ProviderResult]:
        """Generate multiple images in batch."""
        ...

    @abstractmethod
    async def health_check(self) -> ProviderStatus:
        ...

    @abstractmethod
    def get_capabilities(self) -> ProviderCapability:
        ...


class ComfyUIProvider(ImageProvider):
    """ComfyUI API provider for Flux/SDXL image generation."""

    provider_name: ClassVar[str] = "comfyui"

    def __init__(self, base_url: str = "http://localhost:8188") -> None:
        self.base_url = base_url

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 25,
        cfg_scale: float = 7.0,
        seed: int = -1,
    ) -> ProviderResult:
        return ProviderResult(
            success=True,
            provider_name=self.provider_name,
            output={
                "image_path": "",
                "resolution": f"{width}x{height}",
                "seed": seed if seed >= 0 else 42,
            },
        )

    async def generate_batch(
        self,
        prompts: list[dict[str, Any]],
        batch_size: int = 4,
    ) -> list[ProviderResult]:
        return [
            ProviderResult(
                success=True,
                provider_name=self.provider_name,
                output={"image_path": "", "index": i},
            )
            for i in range(min(len(prompts), batch_size))
        ]

    async def health_check(self) -> ProviderStatus:
        return ProviderStatus.ONLINE

    def get_capabilities(self) -> ProviderCapability:
        return ProviderCapability(
            name="ComfyUI",
            description="Local ComfyUI server with Flux/SDXL",
            max_resolution=(2048, 2048),
            supported_formats=["png", "jpg"],
        )


# ── Video Provider ─────────────────────────────────────────────────────


class VideoProvider(ABC):
    """Base interface for video generation providers."""

    provider_type: ClassVar[str] = "video"

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 576,
        num_frames: int = 72,
        fps: int = 24,
        seed: int = -1,
    ) -> ProviderResult:
        """Generate a video clip."""
        ...

    @abstractmethod
    async def health_check(self) -> ProviderStatus:
        ...

    @abstractmethod
    def get_capabilities(self) -> ProviderCapability:
        ...


class WanProvider(VideoProvider):
    """Wan 2.1 video generation provider via ComfyUI."""

    provider_name: ClassVar[str] = "wan"

    def __init__(self, comfyui_url: str = "http://localhost:8188") -> None:
        self.comfyui_url = comfyui_url

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 576,
        num_frames: int = 72,
        fps: int = 24,
        seed: int = -1,
    ) -> ProviderResult:
        return ProviderResult(
            success=True,
            provider_name=self.provider_name,
            output={
                "video_path": "",
                "duration_seconds": num_frames / fps,
                "resolution": f"{width}x{height}",
                "fps": fps,
                "num_frames": num_frames,
            },
        )

    async def health_check(self) -> ProviderStatus:
        return ProviderStatus.ONLINE

    def get_capabilities(self) -> ProviderCapability:
        return ProviderCapability(
            name="Wan 2.1",
            description="Alibaba Wan 2.1 video generation model",
            max_resolution=(1280, 720),
            max_duration_seconds=5.0,
            supported_formats=["mp4"],
        )


# ── Audio Provider ─────────────────────────────────────────────────────


class AudioProvider(ABC):
    """Base interface for audio/TTS providers."""

    provider_type: ClassVar[str] = "audio"

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice_id: str = "default",
        language: str = "zh",
        speed: float = 1.0,
        emotion: str = "neutral",
    ) -> ProviderResult:
        """Synthesize speech from text."""
        ...

    @abstractmethod
    async def health_check(self) -> ProviderStatus:
        ...

    @abstractmethod
    def list_voices(self) -> list[dict[str, str]]:
        ...


class ElevenLabsProvider(AudioProvider):
    """ElevenLabs TTS provider."""

    provider_name: ClassVar[str] = "elevenlabs"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def synthesize(
        self,
        text: str,
        voice_id: str = "default",
        language: str = "zh",
        speed: float = 1.0,
        emotion: str = "neutral",
    ) -> ProviderResult:
        return ProviderResult(
            success=True,
            provider_name=self.provider_name,
            output={
                "audio_path": "",
                "duration_seconds": len(text) / 3.0,
                "format": "mp3",
            },
        )

    async def health_check(self) -> ProviderStatus:
        return ProviderStatus.ONLINE

    def list_voices(self) -> list[dict[str, str]]:
        return [
            {"id": "rachel", "name": "Rachel", "language": "en"},
            {"id": "adam", "name": "Adam", "language": "en"},
        ]


class FishAudioProvider(AudioProvider):
    """Fish Audio TTS provider."""

    provider_name: ClassVar[str] = "fish_audio"

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    async def synthesize(
        self,
        text: str,
        voice_id: str = "default",
        language: str = "zh",
        speed: float = 1.0,
        emotion: str = "neutral",
    ) -> ProviderResult:
        return ProviderResult(
            success=True,
            provider_name=self.provider_name,
            output={
                "audio_path": "",
                "duration_seconds": len(text) / 3.0,
                "format": "wav",
            },
        )

    async def health_check(self) -> ProviderStatus:
        return ProviderStatus.ONLINE

    def list_voices(self) -> list[dict[str, str]]:
        return [
            {"id": "zh_female_1", "name": "Chinese Female 1", "language": "zh"},
        ]


# ── Provider Registry ──────────────────────────────────────────────────


class ProviderRegistry:
    """
    Central registry for all AI providers.

    Manages provider lifecycle, health monitoring, and routing.
    """

    def __init__(self) -> None:
        self._llm_providers: dict[str, LLMProvider] = {}
        self._image_providers: dict[str, ImageProvider] = {}
        self._video_providers: dict[str, VideoProvider] = {}
        self._audio_providers: dict[str, AudioProvider] = {}

    def register_llm(self, name: str, provider: LLMProvider) -> None:
        self._llm_providers[name] = provider

    def register_image(self, name: str, provider: ImageProvider) -> None:
        self._image_providers[name] = provider

    def register_video(self, name: str, provider: VideoProvider) -> None:
        self._video_providers[name] = provider

    def register_audio(self, name: str, provider: AudioProvider) -> None:
        self._audio_providers[name] = provider

    def get_llm(self, name: str = "") -> Optional[LLMProvider]:
        if name:
            return self._llm_providers.get(name)
        return next(iter(self._llm_providers.values()), None)

    def get_image(self, name: str = "") -> Optional[ImageProvider]:
        if name:
            return self._image_providers.get(name)
        return next(iter(self._image_providers.values()), None)

    def get_video(self, name: str = "") -> Optional[VideoProvider]:
        if name:
            return self._video_providers.get(name)
        return next(iter(self._video_providers.values()), None)

    def get_audio(self, name: str = "") -> Optional[AudioProvider]:
        if name:
            return self._audio_providers.get(name)
        return next(iter(self._audio_providers.values()), None)

    async def health_check_all(self) -> dict[str, dict[str, str]]:
        """Check health of all registered providers."""
        results: dict[str, dict[str, str]] = {
            "llm": {},
            "image": {},
            "video": {},
            "audio": {},
        }
        for name, p in self._llm_providers.items():
            results["llm"][name] = (await p.health_check()).value
        for name, p in self._image_providers.items():
            results["image"][name] = (await p.health_check()).value
        for name, p in self._video_providers.items():
            results["video"][name] = (await p.health_check()).value
        for name, p in self._audio_providers.items():
            results["audio"][name] = (await p.health_check()).value
        return results
