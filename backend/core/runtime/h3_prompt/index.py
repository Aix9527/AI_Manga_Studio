"""H3 模板索引构建（GPT 设计）

生成：
- templates_index.json（category_index + tag_index）
- categories.yaml（分类 → 中文描述）
- online_sources.json（150 条作者提示词线上来源清单）
"""
import json

import os

import yaml


PROMPTS_DIR=os.path.join(
    "backend",
    "production",
    "h3_prompts"
)

LIBRARY=os.path.join(
    PROMPTS_DIR,
    "library.json"
)

CATEGORY_LABELS={

    "animation_anime":
    "动画与二次元",

    "character_performance":
    "人物与表演",

    "cinematic":
    "电影与叙事",

    "vfx_transitions":
    "特效与转场",

    "product_ads":
    "广告与产品",

    "dialogue_sound":
    "对白与音效",

    "camera_motion":
    "镜头运动",

    "editing":
    "视频编辑",

    "animal":
    "动物"

}


class H3TemplateIndexer:
    """
    从 library.json 构建双重索引
    """


    def build(
        self
    ):


        lib=json.load(
            open(
                LIBRARY,
                encoding="utf-8"
            )
        )


        entries=lib["entries"]


        category_index={}

        tag_index={}

        for e in entries:

            category_index.setdefault(
                e["category"],
                []
            ).append(
                e["id"]
            )

            for tag in e.get(
                "tags",
                []
            ):

                tag_index.setdefault(
                    tag,
                    []
                ).append(
                    e["id"]
                )


        index={

        "category_index":
        category_index,

        "tag_index":
        tag_index,

        "library_version":
        lib.get(
            "version",
            "1.0.0"
        )

        }


        self._write(
            "templates_index.json",
            index
        )


        # categories.yaml
        categories={

        "categories":

        {

            cat:{

                "label":
                CATEGORY_LABELS.get(
                    cat,
                    cat
                ),

                "count":
                len(
                    category_index[cat]
                )

            }

            for cat in category_index

        }

        }


        self._write_yaml(
            "categories.yaml",
            categories
        )


        # online_sources.json（150 条作者提示词 → 线上图库待导入）
        online={

        "source":
        "tryminimax.asia/zh/minimax-h3-prompts",

        "status":
        "pending_import",

        "license":
        "review_required",

        "total_online":
        222,

        "reconstructed_local":
        len(entries),

        "author_original_pending":
        150,

        "url":
        "https://tryminimax.asia/zh/minimax-h3-prompts",

        "fetch_pages":
        10

        }


        self._write(
            "online_sources.json",
            online
        )


        return index


    def _write(
        self,
        filename,
        payload
    ):


        path=os.path.join(
            PROMPTS_DIR,
            filename
        )


        with open(
            path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                payload,
                f,
                ensure_ascii=False,
                indent=2
            )


        return path


    def _write_yaml(
        self,
        filename,
        payload
    ):


        path=os.path.join(
            PROMPTS_DIR,
            filename
        )


        with open(
            path,
            "w",
            encoding="utf-8"
        ) as f:

            yaml.safe_dump(
                payload,
                f,
                allow_unicode=True,
                sort_keys=False
            )


        return path


def build_index():

    return H3TemplateIndexer().build()


if __name__ == "__main__":

    print(
        build_index()
    )
