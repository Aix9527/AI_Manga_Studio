from pathlib import Path


class NarrativeParser:



    def parse_file(
        self,
        path:str
    ):


        file=Path(path)


        suffix=file.suffix.lower()



        if suffix==".txt":

            return self.parse_text(
                file.read_text(
                    encoding="utf-8"
                )
            )



        if suffix==".md":

            return self.parse_text(
                file.read_text(
                    encoding="utf-8"
                )
            )



        if suffix==".json":

            import json

            return json.loads(

                file.read_text(
                    encoding="utf-8"
                )

            )



        raise ValueError(
            "unsupported format"
        )



    def parse_text(
        self,
        text:str
    ):


        chapters=[]


        current=[]


        for line in text.splitlines():


            line=line.strip()


            if not line:

                continue


            if (
                line.startswith("第")
                and
                "章" in line
            ):


                if current:

                    chapters.append(
                        "\n".join(current)
                    )


                current=[]


            else:

                current.append(line)



        if current:

            chapters.append(
                "\n".join(current)
            )


        return {


            "chapters":

            chapters

        }
