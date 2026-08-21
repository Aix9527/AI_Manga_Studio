import hashlib


from ..domain.ids import create_id


from ..storage.narrative_models import (

NarrativeImportRecord,

StoryDraftRecord,

EpisodeDraftRecord,

SceneDraftRecord,

ShotDraftRecord

)



class NarrativeImporter:



    def __init__(
        self,
        db
    ):

        self.db=db



    def sha256(
        self,
        data
    ):

        return hashlib.sha256(
            data
        ).hexdigest()



    def import_story(
        self,
        project_id,
        filename,
        content,
        episodes
    ):


        digest=self.sha256(
            content
        )


        exists=(

            self.db.query(
                NarrativeImportRecord
            )

            .filter_by(
                project_id=project_id,
                sha256=digest
            )

            .first()

        )


        if exists:

            return exists.id



        imp=NarrativeImportRecord(

            id=create_id(
                "narrative"
            ),

            project_id=project_id,

            filename=filename,

            sha256=digest

        )


        self.db.add(
            imp
        )



        story=StoryDraftRecord(

            id=create_id(
                "story"
            ),

            project_id=project_id,

            title=filename,

            summary=""

        )


        self.db.add(
            story
        )



        for ep in episodes:


            episode=EpisodeDraftRecord(

                id=create_id(
                    "episode_draft"
                ),

                story_id=story.id,

                index=ep["index"],

                title=ep["title"]

            )


            self.db.add(
                episode
            )



            for scene in ep["scenes"]:


                scene_obj=SceneDraftRecord(

                    id=create_id(
                        "scene_draft"
                    ),

                    episode_id=episode.id,

                    index=scene["index"],

                    description=
                    scene["description"]

                )


                self.db.add(
                    scene_obj
                )



                for shot in scene["shots"]:


                    self.db.add(

                        ShotDraftRecord(

                            id=create_id(
                                "shot_draft"
                            ),

                            scene_id=scene_obj.id,

                            index=shot["index"],

                            description=
                            shot["description"],

                            camera=
                            shot["camera"],

                            prompt_hint=
                            shot["prompt_hint"]

                        )

                    )


        self.db.commit()


        return imp.id
