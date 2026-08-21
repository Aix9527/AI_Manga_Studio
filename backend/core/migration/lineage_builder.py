from ..storage.asset_repository import AssetRepository



class LineageBuilder:


    def __init__(
        self,
        db
    ):

        self.repo=AssetRepository(
            db
        )



    def keyframe_to_video(
        self,
        keyframe,
        video
    ):


        return self.repo.create_lineage(

            keyframe.id,

            video.id,

            "keyframe_to_video"

        )



    def video_to_episode(
        self,
        video,
        episode_id
    ):


        return self.repo.create_lineage(

            video.id,

            episode_id,

            "video_to_episode"

        )
