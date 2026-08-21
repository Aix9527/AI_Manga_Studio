"""AI Manga Studio integration modules.

Five integration layers applied in priority order during video generation:

1. OpenMontage  - 7-dimensional provider scoring & tool registry
2. LocalDrama   - Professional shot type/angle/movement storyboard rules
3. Cinema DNA   - Cinematic prompt enhancement (composition, mood, color)
4. MiniMax H3   - API-based video generation (2K/15s, native audio, tail-frame)
5. Seedance 2.0 - API-based video generation via Volcengine Ark (1080p/15s, tail-frame)

Usage:
    from backend.integrations.cinema_dna import get_enhancer
    from backend.integrations.localdrama import SHOT_TYPES
    from backend.integrations.openmontage import registry
    from backend.integrations.minimax_h3 import MiniMaxH3Provider
    from backend.integrations.seedance import SeedanceProvider
"""

# -- Cinema DNA (电影感) ----------------------------------------------------
from backend.integrations.cinema_dna import (
    CinemaPromptEnhancer,
    CompositionPressure,
    TriptychStructure,
    DirectorDNA,
    ColorGradingMethod,
    ColorContinuity,
    CaptureSubstrate,
    ShotScale,
    COMPOSITION_PRESSURES,
    TRIPTYCH_STRUCTURES,
    DIRECTOR_DNA_PROFILES,
    LENS_SPECS,
    COLOR_GRADING_METHODS,
    COLOR_CONTINUITY_METHODS,
    DEFAULT_COLOR_PALETTES,
    CAPTURE_SUBSTRATES,
    ANTI_AI_FORBIDDEN_TERMS,
    ANTI_AI_FORBIDDEN_WORDS,
    ENGLISH_BASE_POSITIVE,
    ENGLISH_BASE_NEGATIVE,
    CameraSpec,
    ColorGrade,
    CompositionInfo,
    EnhancedKeyframePrompt,
    EnhancedVideoPrompt,
    MotionEnhancement,
    TriptychShot,
    DirectorDNAProfile,
    get_enhancer,
    enhance_keyframe,
)

# -- OpenMontage -----------------------------------------------------------
from backend.integrations.openmontage import (
    VideoProviderRegistry,
    ProviderScoring,
    ProviderScoreBreakdown,
    ProviderCapabilities,
    ProviderConfig,
    RegisteredProvider,
    TaskParams,
    ProviderStatus,
    ProviderRuntime,
    ProviderStability,
    registry,
)

# -- LocalMiniDrama --------------------------------------------------------
from backend.integrations.localdrama import (
    SHOT_TYPES,
    CAMERA_MOVEMENTS,
    VERTICAL_ANGLES,
)

# -- MiniMax H3 ------------------------------------------------------------
from backend.integrations.minimax_h3 import (
    MiniMaxH3Provider,
    check_availability as check_minimax_available,
)

# -- Seedance 2.0 ----------------------------------------------------------
from backend.integrations.seedance import (
    SeedanceProvider,
    check_availability as check_seedance_available,
)

__all__ = [
    # Cinema DNA
    "CinemaPromptEnhancer",
    "CompositionPressure",
    "TriptychStructure",
    "DirectorDNA",
    "ColorGradingMethod",
    "ColorContinuity",
    "CaptureSubstrate",
    "ShotScale",
    "COMPOSITION_PRESSURES",
    "TRIPTYCH_STRUCTURES",
    "DIRECTOR_DNA_PROFILES",
    "LENS_SPECS",
    "COLOR_GRADING_METHODS",
    "COLOR_CONTINUITY_METHODS",
    "DEFAULT_COLOR_PALETTES",
    "CAPTURE_SUBSTRATES",
    "ANTI_AI_FORBIDDEN_TERMS",
    "ANTI_AI_FORBIDDEN_WORDS",
    "ENGLISH_BASE_POSITIVE",
    "ENGLISH_BASE_NEGATIVE",
    "CameraSpec",
    "ColorGrade",
    "CompositionInfo",
    "EnhancedKeyframePrompt",
    "EnhancedVideoPrompt",
    "MotionEnhancement",
    "TriptychShot",
    "DirectorDNAProfile",
    "get_enhancer",
    "enhance_keyframe",
    # OpenMontage
    "VideoProviderRegistry",
    "ProviderScoring",
    "ProviderScoreBreakdown",
    "ProviderCapabilities",
    "ProviderConfig",
    "RegisteredProvider",
    "TaskParams",
    "ProviderStatus",
    "ProviderRuntime",
    "ProviderStability",
    "registry",
    # LocalDrama
    "SHOT_TYPES",
    "CAMERA_MOVEMENTS",
    "VERTICAL_ANGLES",
    # MiniMax H3
    "MiniMaxH3Provider",
    "check_minimax_available",
    # Seedance 2.0
    "SeedanceProvider",
    "check_seedance_available",
]
