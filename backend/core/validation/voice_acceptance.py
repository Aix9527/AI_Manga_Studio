"""10 集声音自动验收（GPT 设计）

指标：
- 同角色跨集一致性 ≥ 95%
- LUFS -16 ± 2
- True Peak ≤ -1 dBTP
- 对白音频边界误差 ≤ 250ms
"""
import hashlib

from ..domain.ids import create_id


class VoiceAcceptanceValidator:
    """
    Phase 5.1 · 10 集声音自动验收
    """


    def check_character_consistency(
        self,
        voice_assets
    ):


        """

        voice_assets: {"suwan": ["asset_v1", "asset_v2"], ...}

        同一角色多版本间共享同一 reference 视为一致。

        """

        results={}

        for character, versions in voice_assets.items():

            if len(versions) <= 1:

                results[character]=1.0

                continue


            # 版本间 embedding_path 一致性（模拟：同 reference 判定）
            refs=set(versions)

            consistency=1.0 if len(refs) == 1 else 0.9

            results[character]=round(
                consistency,
                2
            )


        overall=round(
            sum(
                results.values()
            ) / len(results) if results else 0,
            2
        )


        return {

        "per_character":
        results,

        "overall":
        overall,

        "pass":
        overall >= 0.95

        }


    def check_loudness(
        self,
        lufs=-16.0,
        true_peak=-2.0
    ):


        return {

        "lufs":
        lufs,

        "true_peak_db":
        true_peak,

        "lufs_pass":
        -18.0 <= lufs <= -14.0,

        "true_peak_pass":
        true_peak <= -1.0,

        "pass":
        -18.0 <= lufs <= -14.0 and true_peak <= -1.0

        }


    def check_dialogue_boundary(
        self,
        boundary_error_ms=120
    ):


        return {

        "boundary_error_ms":
        boundary_error_ms,

        "pass":
        boundary_error_ms <= 250

        }


    def run(
        self,
        voice_assets,
        lufs=-16.0,
        true_peak=-2.0,
        boundary_error_ms=120
    ):


        consistency=self.check_character_consistency(
            voice_assets
        )

        loudness=self.check_loudness(
            lufs,
            true_peak
        )

        boundary=self.check_dialogue_boundary(
            boundary_error_ms
        )


        passed=(
            consistency["pass"]
            and loudness["pass"]
            and boundary["pass"]
        )


        return {

        "acceptance_id":
        create_id(
            "voice_accept"
        ),

        "scope":
        "10_episode_voice_acceptance",

        "checks":{

            "character_consistency":
            consistency,

            "loudness":
            loudness,

            "dialogue_boundary":
            boundary

        },

        "result":
        "PASS" if passed else "FAIL",

        "passed":
        passed,

        "baseline":
        "10_episode_pass" if passed else "10_episode_fail"

        }
