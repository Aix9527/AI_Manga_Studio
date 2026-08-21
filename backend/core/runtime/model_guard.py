import hashlib

from pathlib import Path



class RuntimeModelGuard:



    def sha256(
        self,
        path
    ):


        h=hashlib.sha256()


        with open(
            path,
            "rb"
        ) as f:


            for chunk in iter(
                lambda:
                f.read(1024*1024),
                b""
            ):

                h.update(chunk)


        return h.hexdigest()



    def verify(
        self,
        path,
        expected
    ):


        file=Path(path)


        if not file.exists():

            return {

            "ok":False,

            "reason":
            "missing"

            }



        actual=self.sha256(
            path
        )


        return {

        "ok":
        actual==expected,

        "sha256":
        actual

        }
