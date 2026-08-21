"""Scene Memory：场景视觉 DNA 存取（GPT 设计）

SceneBible：
    location_id → SceneVisualDNA（architecture/lighting/color/camera/fixed_objects）

解决场景漂移：同一场景多镜头共享同一 DNA，提示词注入固定描述
"""
import json
import os
import threading
import time

from .context_schema import (
    SceneVisualDNA
)


DEFAULT_PATH=os.path.join(
    "storage",
    "scene_memory.json"
)


class SceneMemory:

    def __init__(self, path=DEFAULT_PATH):

        self.path=path

        self._lock=threading.RLock()

        self._data=self._load()


    def _load(self):


        if not os.path.exists(
            self.path
        ):

            return {

            "scenes":
            {}

            }


        try:

            return json.load(
                open(
                    self.path,
                    encoding="utf-8"
                )
            )

        except Exception:

            return {

            "scenes":
            {}

            }


    def _save(self):


        os.makedirs(
            os.path.dirname(
                self.path
            ),
            exist_ok=True
        )


        with open(
            self.path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                self._data,
                f,
                ensure_ascii=False,
                indent=2
            )


    def upsert(
        self,
        dna: SceneVisualDNA
    ):

        with self._lock:

            self._data["scenes"][
                dna.location_id
            ]=dna.__dict__

            self._save()


        return dna


    def get(
        self,
        location_id
    ):


        with self._lock:

            # 支持跨进程/跨请求刷新
            self._data=self._load()

            raw=self._data["scenes"].get(
                location_id
            )


        if not raw:

            return None


        return SceneVisualDNA(**raw)


    def list(self):


        with self._lock:

            self._data=self._load()

            return list(
                self._data["scenes"].values()
            )


    def to_prompt_block(
        self,
        location_id,
        fallback_name=""
    ):


        dna=self.get(
            location_id
        )

        if not dna:

            return ""


        lines=[]

        name=dna.name or fallback_name or dna.location_id

        lines.append(
            f"Location: {name} (visual identity must stay fixed across all shots)"
        )

        if dna.architecture:

            lines.append(
                "Architecture: " + ", ".join(
                    dna.architecture
                )
            )

        if dna.lighting:

            lines.append(
                "Lighting: " + ", ".join(
                    dna.lighting
                )
            )

        if dna.color:

            lines.append(
                "Color palette: " + ", ".join(
                    dna.color
                )
            )

        if dna.camera:

            lines.append(
                "Camera language: " + dna.camera
            )

        if dna.fixed_objects:

            lines.append(
                "Fixed objects (must remain): " + ", ".join(
                    dna.fixed_objects
                )
            )

        if dna.description:

            lines.append(
                "Scene description: " + dna.description
            )


        return "\n".join(
            lines
        )


scene_memory=SceneMemory()
