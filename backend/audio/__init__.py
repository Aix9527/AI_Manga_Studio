"""Audio generation module for AI Manga Studio.

Provides:
- TTSEngine: edge-tts + CosyVoice 2 voice cloning
- SFXEngine: procedural sound effects
- VoiceCloningProvider: zero-shot voice cloning (CosyVoice 2)
- VoiceDesigner: archetype-based voice profile management
"""

from backend.audio.tts_engine import TTSEngine, SFXEngine  # noqa: F401