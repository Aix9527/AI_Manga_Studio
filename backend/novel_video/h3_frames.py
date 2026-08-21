"""H3 frame-count and deterministic seed helpers."""

KNOWN_FRAMES = {5: 124, 10: 243, 15: 362}


def legal_h3_frames(seconds: float, fps: int = 24) -> int:
    """Return the nearest H3-valid ``17n + 5`` frame count."""
    if not 5 <= seconds <= 15 or fps != 24:
        raise ValueError("H3 segments require 5-15 seconds at 24 fps")
    if seconds in KNOWN_FRAMES:
        return KNOWN_FRAMES[seconds]
    target = round(seconds * fps)
    n = max(0, round((target - 5) / 17))
    return 17 * n + 5


def derive_shot_seed(base_seed: int, sequence: int) -> int:
    """Derive a stable, bounded seed for a one-indexed shot sequence."""
    return (base_seed + sequence - 1) % (2**63 - 1)
