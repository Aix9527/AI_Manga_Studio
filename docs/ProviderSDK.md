---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: ac05b1368557ee08912a0f1b051adb10_2c352e3186a911f18766525400f8a581
    ReservedCode1: k5dSk3tKj2vzs46xbVYva8quJXnnrovnazvIH4v3riReD9bCKVy2A3evEw9IPGFEKrj/1aXys+LQO+lQQQuzqKuFhTPdh8M11my2umIsVUGzxrxbJ1FYqCL/lk9PClcad/YUUq6w9O66Y3EbOt8TerIYEqO2nz0YPv01TP5t/FPT9k09NN5A+K1yBjU=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: ac05b1368557ee08912a0f1b051adb10_2c352e3186a911f18766525400f8a581
    ReservedCode2: k5dSk3tKj2vzs46xbVYva8quJXnnrovnazvIH4v3riReD9bCKVy2A3evEw9IPGFEKrj/1aXys+LQO+lQQQuzqKuFhTPdh8M11my2umIsVUGzxrxbJ1FYqCL/lk9PClcad/YUUq6w9O66Y3EbOt8TerIYEqO2nz0YPv01TP5t/FPT9k09NN5A+K1yBjU=
---

# Provider SDK | AI Provider 接口定义

## Overview

The Provider SDK defines the standard interfaces that all AI model integrations must implement. It decouples the core pipeline from specific AI services, allowing any model to be swapped in without modifying workflow logic.

## Responsibilities

- Define abstract base classes for all provider types
- Standardize input/output formats across providers
- Handle provider-specific authentication and configuration
- Manage API rate limiting and retry logic
- Provide capability detection for intelligent routing

## Provider Types

### ImageProvider

```python
from abc import ABC, abstractmethod
from typing import List, Optional
from pathlib import Path

class ImageProvider(ABC):
    """Abstract base class for image generation providers."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        width: int = 1024,
        height: int = 576,
        seed: Optional[int] = None,
        steps: int = 30,
        cfg_scale: float = 7.0,
        **kwargs
    ) -> List[Path]:
        """Generate one or more images from prompts.

        Returns:
            List of paths to generated image files.
        """
        ...

    @abstractmethod
    async def get_capabilities(self) -> ProviderCapabilities:
        """Return the capabilities of this provider."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique provider identifier."""
        ...

class ProviderCapabilities:
    max_resolution: tuple[int, int]
    supported_aspect_ratios: List[str]
    supports_img2img: bool
    supports_inpainting: bool
    supports_controlnet: bool
    max_batch_size: int
    estimated_cost_per_image: Optional[float]
```

### VideoProvider

```python
class VideoProvider(ABC):
    """Abstract base class for video generation providers."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        motion_prompt: Optional[str] = None,
        reference_images: Optional[List[Path]] = None,
        duration_seconds: float = 5.0,
        fps: int = 24,
        width: int = 1920,
        height: int = 1080,
        seed: Optional[int] = None,
        **kwargs
    ) -> Path:
        """Generate a video from prompts and/or reference images.

        Returns:
            Path to generated video file.
        """
        ...

    @abstractmethod
    async def get_capabilities(self) -> ProviderCapabilities:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...
```

### LLMProvider

```python
class LLMProvider(ABC):
    """Abstract base class for language model providers."""

    @abstractmethod
    async def chat(
        self,
        messages: List[dict],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[str] = None,  # "json_object" for structured output
        **kwargs
    ) -> LLMResponse:
        """Send a chat completion request.

        Returns:
            LLMResponse with text content and usage metadata.
        """
        ...

    @abstractmethod
    async def get_capabilities(self) -> ProviderCapabilities:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

class LLMResponse:
    content: str
    model: str
    usage: dict  # {"prompt_tokens": N, "completion_tokens": M}
    finish_reason: str
```

### AudioProvider

```python
class AudioProvider(ABC):
    """Abstract base class for audio/voice generation providers."""

    @abstractmethod
    async def text_to_speech(
        self,
        text: str,
        voice_id: str,
        speed: float = 1.0,
        emotion: Optional[str] = None,
        **kwargs
    ) -> Path:
        """Convert text to speech audio.

        Returns:
            Path to generated audio file.
        """
        ...

    @abstractmethod
    async def get_available_voices(self) -> List[VoiceProfile]:
        """List available voice profiles."""
        ...

    @abstractmethod
    async def get_capabilities(self) -> ProviderCapabilities:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

class VoiceProfile:
    voice_id: str
    name: str
    language: str
    gender: str
    age_range: str
    styles: List[str]  # e.g., ["narration", "conversational", "dramatic"]
```

## Provider Registry

```python
class ProviderRegistry:
    """Central registry for all AI providers."""

    def register(self, provider: Union[ImageProvider, VideoProvider, LLMProvider, AudioProvider]) -> None:
        """Register a provider instance."""
        ...

    def get_image_provider(self, name: str = None) -> ImageProvider:
        """Get an image provider by name, or the default."""
        ...

    def get_video_provider(self, name: str = None) -> VideoProvider:
        ...

    def get_llm_provider(self, name: str = None) -> LLMProvider:
        ...

    def get_audio_provider(self, name: str = None) -> AudioProvider:
        ...

    def list_providers(self, provider_type: str) -> List[str]:
        """List registered provider names for a given type."""
        ...

    def set_default(self, provider_type: str, provider_name: str) -> None:
        """Set the default provider for a given type."""
        ...
```

## Provider Configuration

Providers are configured via YAML:

```yaml
providers:
  llm:
    default: openrouter
    openai:
      api_key: ${OPENAI_API_KEY}
      model: gpt-4o
      base_url: https://api.openai.com/v1
    ollama:
      base_url: http://localhost:11434
      model: llama3.1:70b

  image:
    default: comfyui
    comfyui:
      base_url: http://127.0.0.1:8188
      workflow_template: manga_generation.json

  video:
    default: comfyui_video
    comfyui_video:
      base_url: http://127.0.0.1:8188
      workflow_template: wan_video.json

  audio:
    default: elevenlabs
    elevenlabs:
      api_key: ${ELEVENLABS_API_KEY}
    fish_audio:
      api_key: ${FISH_AUDIO_API_KEY}
```

## Workflow

```
1. Provider Registered → Provider instance created with config
2. Capability Detection → System queries provider capabilities
3. Task Assignment → Workflow engine selects appropriate provider
4. Generate → Provider executes AI generation
5. Retry/Fallback → On failure, retry with backoff or switch to fallback provider
6. Result → Output files returned with metadata
```

## Future

- Provider health monitoring and automatic failover
- Cost tracking and budget enforcement per project
- Provider benchmarking for quality comparison
- Custom provider packaging format for distribution
- Provider marketplace with community ratings
*（内容由AI生成，仅供参考）*
