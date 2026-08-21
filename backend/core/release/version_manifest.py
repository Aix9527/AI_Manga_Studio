import time

from ..domain.ids import create_id



class VersionManifest:
    """
    版本清单：v1.0.0 冻结记录
    """

    def build(
        self
    ):


        return {

            "manifest_id":
            create_id(
                "manifest"
            ),

            "version":
            "1.0.0",

            "status":
            "FROZEN",

            "production_ready":
            True,

            "frozen_at":
            time.strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),

            "release_dir":
            "release/v1.0.0",

            "artifacts":

            [

                "release_report.json",

                "architecture_snapshot.json",

                "database_schema_snapshot.json",

                "route_inventory.json",

                "model_registry_snapshot.json",

                "workflow_registry_snapshot.json",

                "quality_baseline.json",

                "migration_report.json",

                "test_evidence.json",

                "version_manifest.json"

            ]

        }
