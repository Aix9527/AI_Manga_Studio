
"""Seed strategy resolution."""

import hashlib
import random
from dataclasses import dataclass

from backend.modules.generation.domain.plan import SeedPlan, SeedStrategy


@dataclass
class SeedConfig:
    strategy: SeedStrategy = SeedStrategy.RANDOM
    fixed_seed: int | None = None
    candidate_count: int = 4


class SeedResolver:
    """Resolves seed strategy and generates candidate seeds."""

    def resolve(self, config: SeedConfig, target_hash: str = "", character_hash: str = "") -> SeedPlan:
        strategy = config.strategy

        if strategy == SeedStrategy.RANDOM:
            base_seed = random.randint(0, 2**31 - 1)
            return SeedPlan(
                strategy=str(strategy),
                base_seed=base_seed,
                candidate_seeds=tuple(base_seed + i for i in range(config.candidate_count)),
                derivation_input_hash=None,
                provider_managed=False,
            )

        if strategy == SeedStrategy.FIXED and config.fixed_seed is not None:
            return SeedPlan(
                strategy=str(strategy),
                base_seed=config.fixed_seed,
                candidate_seeds=tuple(config.fixed_seed + i for i in range(config.candidate_count)),
                derivation_input_hash=None,
                provider_managed=False,
            )

        if strategy == SeedStrategy.DERIVE_FROM_TARGET:
            base = self._derive_from_hash(target_hash)
            return SeedPlan(
                strategy=str(strategy),
                base_seed=base,
                candidate_seeds=tuple(base + i for i in range(config.candidate_count)),
                derivation_input_hash=target_hash,
                provider_managed=False,
            )

        if strategy == SeedStrategy.DERIVE_FROM_CHARACTER:
            base = self._derive_from_hash(character_hash)
            return SeedPlan(
                strategy=str(strategy),
                base_seed=base,
                candidate_seeds=tuple(base + i for i in range(config.candidate_count)),
                derivation_input_hash=character_hash,
                provider_managed=False,
            )

        if strategy == SeedStrategy.INCREMENTAL_VARIATIONS:
            base = random.randint(0, 2**31 - 1)
            return SeedPlan(
                strategy=str(strategy),
                base_seed=base,
                candidate_seeds=tuple(base + i * 31337 for i in range(config.candidate_count)),
                derivation_input_hash=None,
                provider_managed=False,
            )

        if strategy == SeedStrategy.PROVIDER_MANAGED:
            return SeedPlan(
                strategy=str(strategy),
                base_seed=None,
                candidate_seeds=tuple(None for _ in range(config.candidate_count)),
                derivation_input_hash=None,
                provider_managed=True,
            )

        # Default: random
        base_seed = random.randint(0, 2**31 - 1)
        return SeedPlan(
            strategy="random",
            base_seed=base_seed,
            candidate_seeds=tuple(base_seed + i for i in range(config.candidate_count)),
            derivation_input_hash=None,
            provider_managed=False,
        )

    @staticmethod
    def _derive_from_hash(hash_input: str) -> int:
        if not hash_input:
            return random.randint(0, 2**31 - 1)
        digest = hashlib.sha256(hash_input.encode()).digest()
        return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF
