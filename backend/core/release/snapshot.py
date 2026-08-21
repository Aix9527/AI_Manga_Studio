import time

from ..domain.ids import create_id


class ArchitectureSnapshot:
    """
    架构快照：六层生产架构 + 最终验收层
    """

    LAYERS=[

        "production_core",

        "creative_os",

        "runtime_agent",

        "industrial_quality",

        "media_export",

        "longform_intelligence",

        "validation"

    ]


    def build(self):


        return {

            "snapshot_id":
            create_id(
                "arch"
            ),

            "version":
            "1.0.0",

            "layers":
            self.LAYERS,

            "backend":
            "FastAPI + SQLAlchemy",

            "frontend":
            "React",

            "database":
            "SQLite",

            "generated_at":
            time.strftime(
                "%Y-%m-%dT%H:%M:%S"
            )

        }


class DatabaseSchemaSnapshot:
    """
    数据库快照：全量表清单
    """

    def build(
        self,
        db
    ):


        from sqlalchemy import inspect


        inspector=inspect(
            db.get_bind()
        )


        tables=[]

        for name in inspector.get_table_names():

            tables.append({

                "table":
                name,

                "columns":
                len(
                    inspector.get_columns(
                        name
                    )
                )

            })


        return {

            "snapshot_id":
            create_id(
                "schema"
            ),

            "version":
            "1.0.0",

            "total_tables":
            len(tables),

            "tables":
            tables,

            "generated_at":
            time.strftime(
                "%Y-%m-%dT%H:%M:%S"
            )

        }


class RouteInventory:
    """
    路由清单：全部 API 端点
    """

    def build(
        self,
        app
    ):


        routes=[]

        for route in app.routes:

            if hasattr(
                route,
                "methods"
            ):

                for method in route.methods:

                    if method in (
                        "GET",
                        "POST",
                        "PUT",
                        "DELETE"
                    ):

                        routes.append({

                            "method":
                            method,

                            "path":
                            route.path

                        })


        return {

            "snapshot_id":
            create_id(
                "routes"
            ),

            "version":
            "1.0.0",

            "total_routes":
            len(routes),

            "routes":
            routes,

            "generated_at":
            time.strftime(
                "%Y-%m-%dT%H:%M:%S"
            )

        }


class ModelRegistrySnapshot:
    """
    模型注册表快照：Provider / VRAM 成本
    """

    def build(self):


        from ..longform.vram_predictor import (
            VRAMPredictor
        )


        registry=[]

        for model, base in (
            VRAMPredictor.MODEL_COST.items()
        ):

            registry.append({

                "model":
                model,

                "base_vram_gb":
                base,

                "safe_at_24g":
                base <= 14

            })


        return {

            "snapshot_id":
            create_id(
                "models"
            ),

            "version":
            "1.0.0",

            "total_models":
            len(registry),

            "models":
            registry,

            "generated_at":
            time.strftime(
                "%Y-%m-%dT%H:%M:%S"
            )

        }


class WorkflowRegistrySnapshot:
    """
    工作流注册表快照：核心生产工作流
    """

    def build(self):


        workflows=[

            {
                "id":
                "wf_episode",

                "name":
                "整集生产",

                "steps":
                [
                    "剧本导入",
                    "分镜生成",
                    "镜头渲染",
                    "QC 门禁",
                    "声音合成",
                    "导出封装"
                ]
            },

            {
                "id":
                "wf_shot",

                "name":
                "镜头生产",

                "steps":
                [
                    "画布设计",
                    "镜头生成",
                    "质量门禁",
                    "返工循环"
                ]
            },

            {
                "id":
                "wf_season",

                "name":
                "长剧排产",

                "steps":
                [
                    "整季排产",
                    "资源预测",
                    "切片 DAG",
                    "验收门禁"
                ]
            }

        ]


        return {

            "snapshot_id":
            create_id(
                "workflows"
            ),

            "version":
            "1.0.0",

            "total_workflows":
            len(workflows),

            "workflows":
            workflows,

            "generated_at":
            time.strftime(
                "%Y-%m-%dT%H:%M:%S"
            )

        }
