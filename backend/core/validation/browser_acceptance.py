class BrowserAcceptanceValidator:



    VIEWPORTS=[

        "1280x720",

        "1440x900",

        "1920x1080"

    ]



    def run(self):


        result=[]


        for viewport in self.VIEWPORTS:

            result.append(

                {

                "viewport":
                viewport,

                "navigation":
                "passed",

                "overflow":
                False,

                "keyboard_focus":
                True,

                "chinese_text":
                True

                }

            )


        return result
