from sqlalchemy.orm import Session

from datetime import datetime, timezone

from ..domain.ids import create_id

from .models import (
    ProjectRecord,
    SeasonRecord,
    EpisodeRecord,
    SceneRecord,
    ShotRecord
)



class ProjectRepository:


    def __init__(self, session:Session):

        self.db=session



    def get_or_create_project(
        self,
        name,
        source
    ):


        obj = (
            self.db.query(ProjectRecord)
            .filter_by(
                source_path=source
            )
            .first()
        )


        if obj:

            return obj



        obj=ProjectRecord(

            id=create_id("project"),

            name=name,

            content_type="anime",

            created_at=datetime.now(
                timezone.utc
            ).isoformat(),

            source_path=source
        )


        self.db.add(obj)

        self.db.commit()


        return obj



    def create_default_tree(
        self,
        project
    ):


        old_season = (
            self.db.query(
                SeasonRecord
            )
            .filter_by(
                project_id=project.id
            )
            .first()
        )


        if old_season:

            old_episode = (
                self.db.query(
                    EpisodeRecord
                )
                .filter_by(
                    season_id=old_season.id
                )
                .first()
            )

            if old_episode:

                old_scene = (
                    self.db.query(
                        SceneRecord
                    )
                    .filter_by(
                        episode_id=old_episode.id
                    )
                    .first()
                )

                if old_scene:

                    old_shot = (
                        self.db.query(
                            ShotRecord
                        )
                        .filter_by(
                            scene_id=old_scene.id
                        )
                        .first()
                    )

                    if old_shot:
                        return old_shot

            # broken default tree: remove and rebuild
            self.db.query(ShotRecord).filter_by(scene_id=old_scene.id).delete() if old_scene else None
            if old_scene:
                self.db.query(SceneRecord).filter_by(episode_id=old_episode.id).delete()
            self.db.query(EpisodeRecord).filter_by(season_id=old_season.id).delete()
            self.db.query(SeasonRecord).filter_by(project_id=project.id).delete()
            self.db.commit()



        season=SeasonRecord(

            id=create_id("season"),

            project_id=project.id,

            name="Season 1"
        )


        self.db.add(season)



        episode=EpisodeRecord(

            id=create_id("episode"),

            season_id=season.id,

            title="Episode 1"
        )


        self.db.add(episode)



        scene=SceneRecord(

            id=create_id("scene"),

            episode_id=episode.id,

            location=""
        )


        self.db.add(scene)



        shot=ShotRecord(

            id=create_id("shot"),

            scene_id=scene.id,

            name="Imported Shot",

            status="draft"
        )


        self.db.add(shot)


        self.db.commit()


        return shot
