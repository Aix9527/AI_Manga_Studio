class LoudnessAnalyzer:



    TARGET_LUFS=-16

    MAX_TRUE_PEAK=-1



    def check(
        self,
        lufs,
        true_peak
    ):


        return {


        "lufs_ok":

        abs(
            lufs-self.TARGET_LUFS
        )<=2,


        "peak_ok":

        true_peak<=self.MAX_TRUE_PEAK


        }
