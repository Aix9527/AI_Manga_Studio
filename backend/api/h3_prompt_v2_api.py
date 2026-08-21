"""v1.0.2 H3 Prompt Intelligence API（GPT 设计）

GET   /api/core/h3/prompts/templates          模板列表
GET   /api/core/h3/prompts/templates/{id}     模板详情
GET   /api/core/h3/prompts/search             搜索
POST  /api/core/h3/prompts/match              小说场景 → 加权匹配
POST  /api/core/h3/prompts/compose            场景 → 组装 H3 提示词 + workflow 请求
POST  /api/core/h3/prompts/compose-batch      整本小说逐章生成
"""
from fastapi import APIRouter

from backend.core.runtime.h3_prompt.registry import (
    H3PromptTemplateRegistry
)

from backend.core.runtime.h3_prompt.extractor import (
    SceneFeatureExtractor
)

from backend.core.runtime.h3_prompt.matcher import (
    H3PromptMatcher
)

from backend.core.runtime.h3_prompt.composer import (
    H3PromptComposer
)

from backend.core.creative.parser import (
    NarrativeParser
)


router=APIRouter()

registry=H3PromptTemplateRegistry()

extractor=SceneFeatureExtractor()

matcher=H3PromptMatcher(extractor)

composer=H3PromptComposer()

narrative_parser=NarrativeParser()


@router.get("/templates")
def list_templates(
    category:str=None
):


    return {

    "version":
    registry.version,

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
def search(
    keyword:str,
    tag:str=None
):


    return {

    "keyword":
    keyword,

    "results":
    registry.search(
        keyword,
        tag
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
def match(
    body:dict
):
    """
    小说场景 → 加权匹配模板

    body: {scene: "...", aspect_ratio: "16:9"}
    """


    return matcher.match(
        body["scene"],
        body.get(
            "aspect_ratio",
            "16:9"
        )
    )


@router.post("/compose")
def compose(
    body:dict
):
    """
    场景 → H3 提示词 + workflow 请求

    body: {scene, character?, setting?, emotion?, dialogue?, voice_reference?, on_screen_text?, duration_s?, aspect_ratio?}
    """


    result=matcher.match(
        body["scene"],
        body.get(
            "aspect_ratio",
            "16:9"
        )
    )


    composed=composer.compose(
        result["template"],
        body["scene"],
        body.get(
            "character"
        ),
        body.get(
            "setting"
        ),
        body.get(
            "emotion"
        ),
        body.get(
            "dialogue"
        ),
        body.get(
            "voice_reference"
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


    composed["match_score"]=result["score"]

    composed["match_features"]=result["features"]


    return composed


@router.post("/compose-batch")
def compose_batch(
    body:dict
):
    """
    上传小说 → 自动匹配 → 逐章组装 H3 提示词

    body: {novel_text, style_hint?, voice_references?}
    """


    parsed=narrative_parser.parse_text(
        body["novel_text"]
    )


    results=[]

    for idx, chapter in enumerate(
        parsed["chapters"],
        1
    ):


        scene=chapter[:800]

        if len(chapter) > 800:

            scene += "\n...(truncated)"


        matched=matcher.match(
            scene,
            body.get(
                "aspect_ratio",
                "16:9"
            )
        )


        composed=composer.compose(
            matched["template"],
            scene,
            voice_reference=(
                body.get(
                    "voice_references",
                    {}
                ).get(
                    matched["features"]["tone"]
                )
            )
        )


        composed["chapter_index"]=idx

        composed["match_score"]=matched["score"]

        composed["match_features"]=matched["features"]

        results.append(
            composed
        )


    return {

    "total_chapters":
    len(
        parsed["chapters"]
    ),

    "results":
    results

    }
