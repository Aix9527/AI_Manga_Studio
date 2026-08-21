from datetime import datetime



class ReleaseGate:



    REQUIRED_CHECKS=[

        "tests",

        "quality",

        "recovery",

        "migration",

        "browser",

        "evidence"

    ]



    def evaluate(
        self,
        checks:dict
    ):


        failed=[]


        for item in self.REQUIRED_CHECKS:

            if not checks.get(
                item,
                False
            ):

                failed.append(
                    item
                )



        return {


            "release":

            len(failed)==0,


            "failed_checks":

            failed,


            "generated_at":

            datetime.utcnow()
            .isoformat()

        }
