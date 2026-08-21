import subprocess



class FFmpegComposer:



    def compose(
        self,
        inputs,
        output
    ):


        cmd=[

            "ffmpeg",

            "-y"

        ]



        for item in inputs:

            cmd.extend(
                [
                    "-i",
                    item
                ]
            )


        cmd.append(
            output
        )


        subprocess.run(
            cmd,
            check=True
        )


        return output
