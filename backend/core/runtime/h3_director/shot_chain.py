"""Shot Continuity Chain（GPT 设计 P1）

镜头结束状态 → 下一镜续接（角色姿态/机位/光线）
"""
import json

import os

import threading

import time


DEFAULT_PATH=os.path.join(
    "storage",
    "shot_chain.json"
)


class ShotChain:

    def __init__(self, path=DEFAULT_PATH):

        self.path=path

        self._lock=threading.RLock()

        self._data=self._load()


    def _load(self):


        if not os.path.exists(
            self.path
        ):

            return {

            "shots":
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

            "shots":
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


    def record_end(
        self,
        shot_id,
        character_pose="",
        camera_position="",
        lighting_state="",
        note="",
        tail_frame="",
        object_state="",
        mode="tail_chain"
    ):

        state={

        "shot_id":
        shot_id,

        "character_pose":
        character_pose,

        "camera_position":
        camera_position,

        "lighting_state":
        lighting_state,

        "object_state":
        object_state,

        "tail_frame":
        tail_frame,

        "mode":
        mode,

        "note":
        note,

        "ended_at":
        time.strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

        }


        with self._lock:

            self._data["shots"][
                shot_id
            ]=state

            self._save()


        return state


    def previous_state(
        self,
        shot_id
    ):

        with self._lock:

            # 跨请求刷新
            self._data=self._load()

            shots=self._data["shots"]


        if not shots:

            return {}


        keys=list(
            shots.keys()
        )


        if shot_id in keys:

            idx=keys.index(
                shot_id
            )

            if idx > 0:

                return shots[
                    keys[idx - 1]
                ]


        # shot 未记录时返回最近一次结束状态（上一镜续接）
        return shots[
            keys[-1]
        ]


    def to_continuity_prompt(
        self,
        shot_id
    ):

        prev=self.previous_state(
            shot_id
        )

        if not prev:

            return ""


        bits=[]

        if prev.get(
            "character_pose"
        ):

            bits.append(
                "Continue from previous shot: character stays in pose " + prev["character_pose"]
            )

        if prev.get(
            "camera_position"
        ):

            bits.append(
                "camera continues from " + prev["camera_position"]
            )

        if prev.get(
            "lighting_state"
        ):

            bits.append(
                "lighting stays " + prev["lighting_state"]
            )


        return " ".join(
            bits
        ) if bits else ""


    def to_reference(
        self,
        shot_id
    ):
        """ShotChain v2：上一镜 tail_frame 参考图（previous frame 视觉锁）"""
        prev=self.previous_state(
            shot_id
        )

        if not prev:

            return ""

        if prev.get(
            "mode"
        ) == "transition":

            # Level C 跳切：不注入尾帧
            return ""

        return prev.get(
            "tail_frame",
            ""
        )


shot_chain=ShotChain()
