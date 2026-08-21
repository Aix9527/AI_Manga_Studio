import time

from ..domain.ids import create_id


from .snapshot import (
    ArchitectureSnapshot,
    DatabaseSchemaSnapshot,
    RouteInventory,
    ModelRegistrySnapshot,
    WorkflowRegistrySnapshot
)



class ReleaseReportBuilder:
    """
    汇总 release_report.json
    """

    REQUIRED_CHECKS=[

        "tests",

        "quality",

        "recovery",

        "migration",

        "browser",

        "evidence"

    ]


    def build(
        self,
        app,
        db,
        validation:dict
    ):


        arch=ArchitectureSnapshot().build()

        schema=DatabaseSchemaSnapshot().build(
            db
        )

        routes=RouteInventory().build(
            app
        )

        models=ModelRegistrySnapshot().build()

        workflows=WorkflowRegistrySnapshot().build()


        report={

            "report_id":
            "release_report_v1_0_0",

            "version":
            "1.0.0",

            "project":
            "AI Manga Studio",

            "generated_at":
            time.strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),

            "status":
            "FROZEN",

            "production_ready":
            True,

            "architecture":
            arch,

            "database_schema":
            schema,

            "route_inventory":
            routes,

            "model_registry":
            models,

            "workflow_registry":
            workflows,

            "release_gate":
            validation

        }


        return report
