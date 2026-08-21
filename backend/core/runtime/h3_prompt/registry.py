"""H3 Prompt Template Registry（GPT 设计）"""
import json

import os


PROMPTS_DIR=os.path.join(
    "backend",
    "production",
    "h3_prompts"
)

LIBRARY=os.path.join(
    PROMPTS_DIR,
    "library.json"
)


class H3PromptTemplateRegistry:
    """
    加载 library.json，按 category / tag 索引

    - list / get / categories / search
    """


    def __init__(self):

        self._load()


    def _load(self):


        lib=json.load(
            open(
                LIBRARY,
                encoding="utf-8"
            )
        )


        self.entries=lib.get(
            "entries",
            []
        )

        self.version=lib.get(
            "version",
            "1.0.0"
        )


    def list_templates(
        self,
        category=None
    ):


        if not category:

            return self.entries


        return [

            e for e in self.entries

            if e["category"] == category

        ]


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
        keyword,
        tag=None
    ):


        kw=keyword.lower()

        results=[]

        for e in self.entries:

            hit=False

            if kw in e["title"].lower():

                hit=True

            if kw in e["style_hint"].lower():

                hit=True

            if tag and tag in e.get(
                "tags",
                []
            ):

                hit=True

            if hit:

                results.append(
                    e
                )


        return results


registry=H3PromptTemplateRegistry()
