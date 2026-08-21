from __future__ import annotations

import shutil
from pathlib import Path

from ..domain.ids import sha256_file


class AssetStore:


    def __init__(self, root):

        self.root = Path(root)

        self.root.mkdir(
            parents=True,
            exist_ok=True
        )


    def save(
        self,
        project_id: str,
        asset_type: str,
        source_file: str
    ):

        digest = sha256_file(
            source_file
        )


        target_dir = (
            self.root
            /
            project_id
            /
            asset_type
            /
            digest
        )


        target_dir.mkdir(
            parents=True,
            exist_ok=True
        )


        target = (
            target_dir
            /
            Path(source_file).name
        )


        if not target.exists():

            shutil.copy2(
                source_file,
                target
            )


        return {

            "path": str(target),

            "sha256": digest
        }
