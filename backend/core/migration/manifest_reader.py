from pathlib import Path
import json



class ManifestReader:


    def read(
        self,
        project_path:Path
    ):


        manifest = (
            project_path
            /
            "gx_manifest.json"
        )


        if not manifest.exists():

            return {}



        return json.loads(
            manifest.read_text(
                encoding="utf-8"
            )
        )
