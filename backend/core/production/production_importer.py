from __future__ import annotations

from ..domain.ids import create_id

from ..storage.models import (
    ShotRecord,
    PromptRecipeRecord,
    WorkflowVersionRecord,
    ModelArtifactRecord,
    ProductionRunRecord,
    QualityEvaluationRecord,
    SceneRecord,
    EpisodeRecord,
    SeasonRecord
)


class ProductionImporter:


    def __init__(
        self,
        db
    ):

        self.db = db



    def normalize_shot_id(
        self,
        item
    ):

        return (
            item.get("id")
            or
            item.get("shot_id")
            or
            item.get("name")
        )



    def get_or_create_shot(
        self,
        project,
        shot_id
    ):


        shot = (
            self.db.query(
                ShotRecord
            )
            .filter_by(
                name=shot_id
            )
            .first()
        )


        if shot:

            return shot



        # find project's default scene
        scene = (
            self.db.query(
                SceneRecord
            )
            .filter(
                SceneRecord.episode_id.in_(
                    [
                        e.id
                        for e in self.db.query(
                            EpisodeRecord
                        )
                        .join(
                            SeasonRecord,
                            SeasonRecord.id ==
                            EpisodeRecord.season_id
                        )
                        .filter(
                            SeasonRecord.project_id ==
                            project.id
                        )
                    ]
                )
            )
            .first()
        )


        if not scene:

            raise RuntimeError(
                f"No scene found for {project.name}"
            )



        shot = ShotRecord(

            id=create_id(
                "shot"
            ),

            scene_id=scene.id,

            name=shot_id,

            status="imported"

        )


        self.db.add(
            shot
        )

        self.db.commit()


        return shot



    def import_shot_contract(
        self,
        project,
        data
    ):


        shots=data.get(
            "shots",
            []
        )


        if not shots:

            return []



        imported=[]


        # manifest top-level model info
        model_info=data.get(
            "model",
            {}
        )



        for item in shots:


            shot_id=self.normalize_shot_id(
                item
            )


            if not shot_id:

                continue



            shot=self.get_or_create_shot(
                project,
                shot_id
            )



            # Production Run
            existing_run=(

                self.db.query(
                    ProductionRunRecord
                )
                .filter_by(
                    shot_id=shot.id
                )
                .first()

            )


            if existing_run:

                run=existing_run

            else:


                run=ProductionRunRecord(

                    id=create_id(
                        "run"
                    ),

                    shot_id=shot.id,


                    seed=str(
                        item.get(
                            "seed",
                            ""
                        )
                    ),


                    cfg=str(
                        item.get(
                            "cfg",
                            item.get(
                                "CFG",
                                ""
                            )
                        )
                    ),


                    steps=str(
                        item.get(
                            "steps",
                            ""
                        )
                    ),


                    motion_profile=str(

                        item.get(
                            "motion_profile",

                            item.get(
                                "motion_level",
                                ""
                            )

                        )

                    )

                )


                self.db.add(
                    run
                )


                self.db.commit()



            # Prompt
            prompt = (

                item.get(
                    "i2v_prompt"
                )

                or

                item.get(
                    "prompt"
                )

                or

                item.get(
                    "prompt_tail"
                )

                or ""

            )


            if prompt:


                exists=(

                    self.db.query(
                        PromptRecipeRecord
                    )
                    .filter_by(
                        shot_id=shot.id
                    )
                    .first()

                )


                if not exists:


                    self.db.add(

                        PromptRecipeRecord(

                            id=create_id(
                                "prompt"
                            ),

                            shot_id=shot.id,

                            prompt_text=prompt,

                            negative_prompt=""

                        )

                    )



            # Workflow
            workflow = (

                item.get(
                    "workflow"
                )
                or
                data.get(
                    "workflow",
                    ""
                )

            )


            if workflow:


                self.db.add(

                    WorkflowVersionRecord(

                        id=create_id(
                            "workflow"
                        ),

                        shot_id=shot.id,

                        workflow_name=str(
                            workflow
                        ),

                        workflow_hash=""

                    )

                )



            # Model SHA
            model_sha = (

                item.get(
                    "model_sha256"
                )

                or

                model_info.get(
                    "sha256",
                    ""
                )

            )


            model_name = (

                model_info.get(
                    "name",
                    ""
                )

                or

                item.get(
                    "model",
                    ""

                )

            )


            if model_sha or model_name:


                self.db.add(

                    ModelArtifactRecord(

                        id=create_id(
                            "model"
                        ),

                        production_run_id=run.id,

                        model_name=str(
                            model_name
                        ),

                        sha256=str(
                            model_sha
                        )

                    )

                )



            # Quality
            score=(

                item.get(
                    "quality_gate_score"
                )

                or

                item.get(
                    "quality",
                    {}
                ).get(
                    "score",
                    ""
                )

            )


            if score:


                exists=(

                    self.db.query(
                        QualityEvaluationRecord
                    )
                    .filter_by(
                        shot_id=shot.id
                    )
                    .first()

                )


                if not exists:


                    self.db.add(

                        QualityEvaluationRecord(

                            id=create_id(
                                "qc"
                            ),

                            shot_id=shot.id,

                            score=str(
                                score
                            ),

                            result="PASS"

                        )

                    )


            imported.append(
                shot_id
            )



        self.db.commit()


        return imported
