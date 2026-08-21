from ..domain.ids import create_id


class ExportService:



    FORMATS={


        "vertical":
        "1080x1920",


        "horizontal":
        "1920x1080",


        "square":
        "1080x1080"

    }



    def prepare(
        self,
        project_id,
        mode
    ):


        return {


        "export_id":
        create_id(
            "export"
        ),


        "project_id":
        project_id,


        "resolution":
        self.FORMATS[mode]


        }
