from __future__ import annotations

import json
from pathlib import Path

from datetime import datetime


ROOT = Path(
    "F:/AI_Manga_Studio"
)


OUTPUT = ROOT / "migration_report.json"


def scan():


    result = {

        "time":
            datetime.now().isoformat(),

        "projects": [],

        "outputs": [],

        "databases": []

    }


    projects = ROOT / "projects"

    outputs = ROOT / "outputs"


    if projects.exists():

        for p in projects.iterdir():

            if p.is_dir():

                result["projects"].append(
                    str(p)
                )


    if outputs.exists():

        for p in outputs.iterdir():

            if p.is_dir():

                result["outputs"].append(
                    str(p)
                )


    for db in ROOT.rglob(
        "*.db"
    ):

        result["databases"].append(
            str(db)
        )


    OUTPUT.write_text(

        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        ),

        encoding="utf-8"

    )


    print(
        "Migration scan complete:"
    )

    print(
        OUTPUT
    )


if __name__ == "__main__":

    scan()
