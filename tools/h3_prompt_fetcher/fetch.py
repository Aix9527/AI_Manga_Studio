"""H3 提示词在线抓取器（GPT 设计）

流程：分页 → HTML 解析 → 提取 title/category/prompt → 保存 raw → 人工 license 确认 → 转换 template

目标：tryminimax.asia 150 条作者原创提示词全文补充
（72 条重构提示词 MIT 全文已在 library.json；作者提示词 license review_required）
"""
import json
import re

import httpx

from bs4 import BeautifulSoup


BASE="https://tryminimax.asia/zh/minimax-h3-prompts"

RAW_DIR=r"f:\AI_Manga_Studio\backend\production\h3_prompts\online_raw"

CATEGORY_ZH={

    "广告与产品":
    "product_ads",

    "电影与叙事":
    "cinematic",

    "对白与音效":
    "dialogue_sound",

    "特效与转场":
    "vfx_transitions",

    "动画与二次元":
    "animation_anime",

    "人物与表演":
    "character_performance",

    "视频编辑":
    "editing",

    "镜头运动":
    "camera_motion",

    "动物":
    "animal",

    "参考与一致性":
    "reference_consistency"

}


def fetch_html(
    url
):


    r=httpx.get(

        url,

        headers={

            "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"

        },

        timeout=25,

        trust_env=False

    )


    return r.text


def parse_page(
    html
):


    soup=BeautifulSoup(
        html,
        "html.parser"
    )


    articles=soup.find_all(
        "article",
        id=re.compile(r"^prompt-")
    )


    entries=[]

    for art in articles:

        pid=art.get(
            "id"
        )

        h=art.find(
            ["h3", "h2"]
        )

        title=h.get_text(
            strip=True
        ) if h else ""


        cats=[

            a.get_text(strip=True)

            for a in art.find_all(
                "a"
            )

            if a.get_text(
                strip=True
            ) in CATEGORY_ZH

        ]


        category=CATEGORY_ZH.get(
            cats[0],
            "cinematic"
        ) if cats else "cinematic"


        texts=[

            t.get_text(
                " ",
                strip=True
            )

            for t in art.find_all(
                ["p", "div"]
            )

            if len(
                t.get_text(
                    " ",
                    strip=True
                )
            ) > 60

        ]


        texts=sorted(
            set(
                texts
            ),
            key=len,
            reverse=True
        )


        entries.append({

            "gallery_id":
            pid,

            "title":
            title,

            "category":
            category,

            "summary":
            texts[1] if len(
                texts
            ) > 1 else texts[0] if texts else "",

            "prompt":
            texts[0] if texts else "",

            "license":
            "review_required",

            "status":
            "raw"

        })


    return entries


def save_raw(
    entries,
    page
):


    import os

    os.makedirs(
        RAW_DIR,
        exist_ok=True
    )


    path=os.path.join(
        RAW_DIR,
        f"page_{page}.json"
    )


    json.dump(

        entries,

        open(
            path,
            "w",
            encoding="utf-8"
        ),

        ensure_ascii=False,

        indent=1

    )


    return path


def main():

    html=fetch_html(
        BASE
    )

    entries=parse_page(
        html
    )

    path=save_raw(
        entries,
        1
    )

    full=[

        e for e in entries

        if len(
            e["prompt"]
        ) > 300

    ]

    print(
        "page 1 entries:",
        len(entries),
        "| saved:",
        path
    )

    print(
        "full prompt (>300 chars):",
        len(full)
    )

    # 提示：分页需浏览器自动化（页面为 JS 分页）
    print(
        "NOTE: pagination is client-side JS; use browser automation to fetch pages 2-10"
    )


if __name__ == "__main__":

    main()
