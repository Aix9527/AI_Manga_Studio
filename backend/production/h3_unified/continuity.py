from __future__ import annotations

MOTION_CONTEXT_NODE_SIGNATURES = {
    "MiniMaxH3MotionContext": {
        "required": {
            "conditioning",
            "vae",
            "latent",
            "context_length",
            "audio_context_length",
        },
        "optional": {
            "context_frames",
            "context_latent",
            "audio_vae",
            "context_audio",
        },
    },
    "MiniMaxH3MotionContextTrim": {
        "required": {"images", "trim_frames"},
        "optional": {"audio", "fps", "match_tail"},
    },
    "MiniMaxH3MotionContextSaveLatent": {
        "required": {"latent", "filename_prefix", "clip_index"},
        "optional": set(),
    },
    "MiniMaxH3MotionContextLoadLatent": {
        "required": {"latent_path", "clip_index"},
        "optional": set(),
    },
}

DEFAULT_VIDEO_CONTEXT_FRAMES = 22
DEFAULT_AUDIO_CONTEXT_FRAMES = 24
