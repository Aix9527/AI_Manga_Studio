"""Reference Selector：从 CharacterBible / Location / Asset 选参考（GPT 设计）

- CharacterBible：views（front）→ 角色身份参考；expressions → 情绪参考；actions → 动作参考
- Location：场景 DNA 描述（无图时用 prompt）
- AssetVersion（DB）：道具/服装资产路径
"""
import os

from backend.characters.bible_v2.repository import (
    CharacterBibleRepository
)

from backend.world.location import (
    LocationStore
)

from backend.core.storage.database import (
    SessionLocal
)

from backend.core.storage.creative_models import (
    LocationVersionRecord
)

from backend.core.storage.asset_repository import (
    AssetVersionRecord
)

from .context_schema import (
    ReferenceItem
)


class ReferenceSelector:
    """
    输入 shot 的角色/地点/道具 → ReferenceItem 列表
    """


    def __init__(self):

        self.bible_repo=CharacterBibleRepository()

        self.locations=LocationStore()


    def character_reference(
        self,
        character_id,
        expression=None
    ):


        items=[]

        bible=self.bible_repo.get(
            character_id
        )


        if bible is None:

            return items


        # 身份参考：front view（优先 image，其次 prompt）
        front=bible.views.get(
            "front"
        )

        if front:

            items.append(

                ReferenceItem(

                    type="character",

                    id=f"{character_id}_front",

                    ref=front.image_path,

                    source="image" if front.image_path else "prompt",

                    prompt=front.prompt,

                    priority=1

                )

            )


        # 情绪参考
        if expression:

            ex=bible.expressions.get(
                expression
            )

            if ex:

                items.append(

                    ReferenceItem(

                        type="expression",

                        id=f"{character_id}_{expression}",

                        ref=ex.image_path,

                        source="image" if ex.image_path else "prompt",

                        prompt=ex.prompt,

                        priority=2

                    )

                )


        return items


    def location_reference(
        self,
        location_id
    ):


        loc=self.locations.get(
            location_id
        )


        if loc is None:

            return []


        prompt_bits=[

            loc.architecture,

            "landmarks: " + ", ".join(
                loc.landmarks
            )

        ]


        return [

            ReferenceItem(

                type="location",

                id=location_id,

                ref="",

                source="prompt",

                prompt="\n".join(

                    b for b in prompt_bits if b

                ),

                priority=1

            )

        ]


    def prop_reference(
        self,
        prop_ids
    ):


        items=[]

        db=SessionLocal()

        try:

            for pid in prop_ids or []:

                rows=db.query(
                    AssetVersionRecord
                ).filter(
                    AssetVersionRecord.asset_id == pid
                ).all()

                for r in rows:

                    items.append(

                        ReferenceItem(

                            type="prop",

                            id=pid,

                            ref=r.asset_path or "",

                            source="image" if r.asset_path else "prompt",

                            prompt=f"prop asset {pid}",

                            priority=3

                        )

                    )

        finally:

            db.close()


        return items


    def select(
        self,
        characters=None,
        expressions=None,
        locations=None,
        props=None
    ):


        items=[]

        for ch, ex in zip(
            characters or [],
            expressions or []
        ):

            items.extend(
                self.character_reference(
                    ch,
                    ex
                )
            )


        for lid in locations or []:

            items.extend(
                self.location_reference(
                    lid
                )
            )


        items.extend(
            self.prop_reference(
                props
            )
        )


        return items


reference_selector=ReferenceSelector()
