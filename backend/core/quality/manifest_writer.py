import json

from pathlib import Path



class ManifestWriter:



    def update_quality(
        self,
        manifest_path,
        shot_id,
        quality
    ):


        path=Path(
            manifest_path
        )


        if path.exists():

            data=json.loads(

                path.read_text(
                    encoding="utf-8"
                )

            )

        else:

            data={}



        shots=data.setdefault(
            "quality_results",
            {}
        )


        shots[shot_id]=quality



        path.write_text(

            json.dumps(
                data,
                ensure_ascii=False,
                indent=2
            ),

            encoding="utf-8"

        )


        return True
