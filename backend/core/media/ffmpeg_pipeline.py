import subprocess



class FFmpegPipeline:



    def compose(
        self,
        video,
        audio_tracks,
        subtitle,
        output
    ):


        cmd=[

            "ffmpeg",

            "-y",

            "-i",

            video

        ]



        for audio in audio_tracks:

            cmd.extend(

                [

                "-i",

                audio

                ]

            )



        filter_complex=[]



        if subtitle:


            filter_complex.append(

                f"subtitles={subtitle}"

            )



        if filter_complex:


            cmd.extend(

                [

                "-vf",

                ",".join(
                    filter_complex
                )

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
