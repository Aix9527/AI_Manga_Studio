import json

from pathlib import Path



class ManifestReader:



    def read(
        self,
        path
    ):


        file=Path(path)


        if not file.exists():

            return {}


        return json.loads(

            file.read_text(
                encoding="utf-8"
            )

        )
