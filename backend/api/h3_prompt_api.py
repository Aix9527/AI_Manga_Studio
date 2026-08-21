"""H3 提示词模板系统 API

GET    /api/core/h3/templates           模板列表（可按分类）
GET    /api/core/h3/templates/categories 分类统计
GET    /api/core/h3/templates/{id}      模板详情
GET    /api/core/h3/templates/search    关键词搜索
POST   /api/core/h3/match               小说场景 → 匹配模板
POST   /api/core/h3/generate            小说场景 → 生成 H3 提示词
POST   /api/core/h3/generate-batch      章节批量生成
"""
from fastapi import APIRouter

from backend.core.runtime.h3_templates.registry import (
    H3PromptTemplateRegistry
)

from backend.core.runtime.h3_templates.matcher import (
    H3TemplateMatcher
)

from backend.core.runtime.h3_templates.assembler import (
    H3PromptAssembler
)

from backend.core.creative.parser import (
    NarrativeParser
)


router=APIRouter()

registry=H3PromptTemplateRegistry()

matcher=H3TemplateMatcher(registry)

assembler=H3PromptAssembler()

narrative_parser=NarrativeParser()


@router.get("/templates")
def list_templates(
    category:str=None
):


    return {

    "total":
    len(
        registry.entries
    ),

    "category":
    category,

    "templates":
    registry.list_templates(
        category
    )

    }


@router.get("/templates/categories")
def template_categories():


    return registry.categories()


@router.get("/templates/search")
def search_templates(
    keyword:str
):


    return {

    "keyword":
    keyword,

    "results":
    registry.search(
        keyword
    )

    }


@router.get("/templates/{template_id}")
def get_template(
    template_id:str
):


    t=registry.get_template(
        template_id
    )


    if not t:

        return {

        "ok":
        False,

        "error":
        "template not found"

        }


    return t


@router.post("/match")
def match_template(
    body:dict
):


    result=matcher.match(
        body["scene"],
        body.get(
            "category"
        ),
        body.get(
            "style_hint"
        )
    )


    return result


@router.post("/generate")
def generate_prompt(
    body:dict
):


    matched=matcher.match(
        body["scene"],
        body.get(
            "category"
        ),
        body.get(
            "style_hint"
        )
    )


    template=matched["template"]


    result=assembler.assemble(
        template,
        body["scene"],
        body.get(
            "character"
        ),
        body.get(
            "setting"
        ),
        body.get(
            "dialogue"
        ),
        body.get(
            "on_screen_text"
        ),
        body.get(
            "duration_s"
        ),
        body.get(
            "aspect_ratio"
        )
    )


    result["matched_category"]=matched["category"]

    result["match_score"]=matched["score"]


    return result


@router.post("/generate-batch")
def generate_batch(
    body:dict
):
    """
    上传小说 → 自动匹配 → 逐章生成 H3 提示词

    body: {novel_text: "...", characters: {...}, style_hint: "..."}
    """


    parsed=narrative_parser.parse_text(
        body["novel_text"]
    )


    chapters=parsed["chapters"]


    results=[]

    for idx, chapter in enumerate(
        chapters,
        1
    ):


        scene=chapter[:800]

        if len(chapter) > 800:

            scene += "\n...(truncated)"


        matched=matcher.match(
            scene,
            style_hint=body.get(
                "style_hint"
            )
        )


        generated=assembler.assemble(
            matched["template"],
            scene,
            body.get(
                "characters",
                {}
            ).get(
                "default"
            ),
            dialogue=body.get(
                "dialogue"
            )
        )


        generated["chapter_index"]=idx

        generated["matched_category"]=matched["category"]

        results.append(
            generated
        )


    return {

    "total_chapters":
    len(chapters),

    "results":
    results

    }
