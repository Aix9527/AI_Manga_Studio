"""H3 提示词模板注册表"""
import json

import os


LIBRARY_PATH=os.path.join(
    "backend",
    "production",
    "h3_prompts",
    "library.json"
)


class H3PromptTemplateRegistry:
    """
    加载 72 条 H3 提示词模板，按分类索引

    - list / get / search
    - categories: 分类统计
    """


    def __init__(self):

        self.library=self._load()


    def _load(self):


        if not os.path.exists(
            LIBRARY_PATH
        ):

            return {

            "entries":
            []

            }


        with open(
            LIBRARY_PATH,
            encoding="utf-8"
        ) as f:

            return json.load(f)


    @property
    def entries(
        self
    ):

        return self.library.get(
            "entries",
            []
        )


    def list_templates(
        self,
        category=None
    ):


        entries=self.entries

        if category:

            entries=[

                e for e in entries

                if e["category"] == category

            ]


        return entries


    def get_template(
        self,
        template_id
    ):


        for e in self.entries:

            if e["id"] == template_id:

                return e


        return None


    def categories(self):


        from collections import Counter

        return dict(

            Counter(
                e["category"]
                for e in self.entries
            )

        )


    def search(
        self,
        keyword
    ):


        kw=keyword.lower()

        return [

            e for e in self.entries

            if kw in e["title"].lower()
            or kw in e["style_hint"].lower()

        ]


registry=H3PromptTemplateRegistry()
