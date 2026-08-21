from __future__ import annotations

import json
from pathlib import Path


class LicenseManifest:


    def __init__(self, path):

        self.path = Path(path)

        self.items = []


    def add(
        self,
        name: str,
        source: str,
        license_name: str,
        usage: str
    ):

        self.items.append({

            "name": name,

            "source": source,

            "license": license_name,

            "usage": usage
        })


    def save(self):

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self.path.write_text(

            json.dumps(
                self.items,
                indent=2,
                ensure_ascii=False
            ),

            encoding="utf-8"
        )


if __name__ == "__main__":

    manifest = LicenseManifest(
        "architecture/license_manifest.json"
    )

    manifest.add(
        "AI Manga Studio",
        "internal",
        "Proprietary",
        "core system"
    )


    manifest.save()

    print(
        "license manifest created"
    )
