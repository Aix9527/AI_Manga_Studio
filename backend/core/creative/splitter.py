class NarrativeSplitter:



    def split(
        self,
        parsed
    ):


        chapters=parsed.get(
            "chapters",
            []
        )


        result=[]


        for idx,ch in enumerate(chapters):


            scenes=[]


            paragraphs=[

                x.strip()

                for x in ch.split("\n")

                if x.strip()

            ]



            for sidx,p in enumerate(paragraphs):


                scenes.append(

                    {

                    "index":
                        sidx+1,

                    "description":
                        p,


                    "shots":

                    [

                    {

                    "index":1,

                    "description":p,

                    "camera":
                    "medium",

                    "prompt_hint":
                    ""

                    }

                    ]

                    }

                )



            result.append(

                {

                "index":
                    idx+1,

                "title":
                    f"Episode {idx+1}",

                "scenes":
                    scenes

                }

            )


        return result
