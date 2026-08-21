from __future__ import annotations

"""Model integrity guard for ComfyUI Wan2.2 assets.

Catches the 2026-08-05 failure mode: a byte-size-valid but hash-corrupted
``wan2.2_ti2v_5B_fp16.safetensors`` produced noise/"QR code" videos across
both the WanVideoWrapper and the official native workflow.  The corruption
only surfaced in the file tail, so size checks are not enough.

Hashes are verified lazily and cached keyed by (path, size, mtime) so that a
10 GB diffusion model is not re-hashed on every video request.
"""

import hashlib
import json
import os
from pathlib import Path

# Official SHA256 (HF LFS oid) of the exact model files production relies on.
EXPECTED_MODELS: dict[str, str] = {
    "wan2.2_ti2v_5B_fp16_fixed.safetensors": (
        "456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d0049a69fcfeca1e"
    ),
    "wan2.2_vae.safetensors": (
        "e40321bd36b9709991dae2530eb4ac303dd168276980d3e9bc4b6e2b75fed156"
    ),
}

# Damaged files that must never be selected for generation.
CORRUPT_MODEL_NAMES: frozenset[str] = frozenset(
    {
        "wan2.2_ti2v_5B_fp16.safetensors",
        "wan2.2_ti2v_5B_fp16.safetensors.corrupt.bak",
    }
)

_CACHE_PATH = Path(
    os.environ.get("WAN_MODEL_HASH_CACHE", "backend/production/.model_hash_cache.json")
)


def sha256_file(path: Path, chunk_size: int = 16 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _load_cache() -> dict:
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(cache: dict) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except OSError:
        pass


def verify_model_file(path: str | Path) -> str:
    """Verify a model file's SHA256 against EXPECTED_MODELS.

    Recomputes the hash only when the file's size or mtime changed since the
    last check.  Raises RuntimeError on mismatch; returns the sha256 on match.
    """
    model_path = Path(path)
    name = model_path.name
    expected = EXPECTED_MODELS.get(name)
    if expected is None:
        # Unknown file: no hash policy for it yet, allow (guard is additive).
        return ""
    if name in CORRUPT_MODEL_NAMES:
        raise RuntimeError(
            f"Blocked damaged Wan model: {name}. "
            f"Use {sorted(EXPECTED_MODELS)} instead."
        )
    if not model_path.is_file():
        raise FileNotFoundError(f"Model not found: {model_path}")

    stat = model_path.stat()
    cache_key = f"{model_path.resolve()}:{stat.st_size}:{int(stat.st_mtime)}"
    cache = _load_cache()
    if cache.get(cache_key) == expected:
        return expected

    actual = sha256_file(model_path)
    if actual.lower() != expected.lower():
        raise RuntimeError(
            f"Model checksum mismatch: {name}\n"
            f"expected={expected}\n"
            f"actual  ={actual}"
        )
    cache[cache_key] = expected
    _save_cache(cache)
    return actual


def assert_models_usable(model_dir: str | Path) -> None:
    """Verify every EXPECTED_MODELS file present under ``model_dir``."""
    root = Path(model_dir)
    for name in EXPECTED_MODELS:
        verify_model_file(root / name)
