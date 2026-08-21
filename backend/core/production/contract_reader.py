from pathlib import Path
import json


class ContractReader:


    def read_json(
        self,
        path:Path
    ):

        if not path.exists():

            return {}


        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )



    def read_yaml(
        self,
        path:Path
    ):

        if not path.exists():

            return {}


        try:

            import yaml

            return yaml.safe_load(
                path.read_text(
                    encoding="utf-8"
                )
            ) or {}

        except Exception:

            return {}
