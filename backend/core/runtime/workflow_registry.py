import json

from pathlib import Path



class WorkflowRegistry:



    def __init__(
        self,
        root="backend/production/workflows"
    ):

        self.root=Path(root)



    def list(
        self
    ):


        if not self.root.exists():

            return []


        return sorted(

            str(
                x.relative_to(
                    self.root
                )
            ).replace(
                "\\",
                "/"
            )

            for x in self.root.rglob(
                "*.json"
            )

        )



    def load(
        self,
        name
    ):


        path=self.root/name


        return json.loads(

            path.read_text(
                encoding="utf-8"
            )

        )
