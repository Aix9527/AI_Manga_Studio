from pathlib import Path


from ..storage.database import (
    init_database,
    SessionLocal
)

from ..storage.models import (
    ProjectRecord,
    EpisodeRecord
)

from .asset_detector import AssetDetector
from .asset_importer import AssetImporter
from .lineage_builder import LineageBuilder
from .lineage_matcher import LineageMatcher
from ..production.contract_reader import ContractReader
from ..production.production_importer import ProductionImporter



ROOT=Path(
    "F:/AI_Manga_Studio/projects"
)



def find_episode(
    db,
    project_id
):

    return (
        db.query(
            EpisodeRecord
        )
        .filter(
            EpisodeRecord.id.in_(
                [
                    e.id
                    for e in db.query(EpisodeRecord).all()
                ]
            )
        )
        .first()
    )



def run():

    init_database()

    db=SessionLocal()


    detector=AssetDetector()

    importer=AssetImporter(
        db
    )


    lineage=LineageBuilder(
        db
    )


    reader=ContractReader()

    production=ProductionImporter(
        db
    )


    for project_path in ROOT.iterdir():


        if not project_path.is_dir():

            continue



        project=(
            db.query(ProjectRecord)
            .filter_by(
                source_path=str(project_path)
            )
            .first()
        )


        if not project:

            continue



        episode=find_episode(
            db,
            project.id
        )



        imported=[]


        for file in detector.scan(
            project_path
        ):

            asset,version=importer.import_file(

                project.id,

                project_path,

                file

            )


            imported.append(
                version
            )


        print(
            project.name,
            "assets:",
            len(imported)
        )


        # ===== lineage =====


        matcher=LineageMatcher()


        pairs=matcher.pair(
            imported
        )


        for image,video in pairs:


            lineage.keyframe_to_video(
                image,
                video
            )


        for video in imported:


            if video.path.endswith(
                ".mp4"
            ):


                lineage.video_to_episode(

                    video,

                    episode.id

                )


        # ===== production contract =====


        manifest_path=(
            project_path
            /
            "gx_manifest.json"
        )


        phase_path=(
            project_path
            /
            "gx_phase4_plan.json"
        )


        contract_path=(
            project_path
            /
            "gx013_030_contract.json"
        )



        for contract in [
            manifest_path,
            phase_path,
            contract_path
        ]:

            data=reader.read_json(
                contract
            )


            if data:

                imported=production.import_shot_contract(

                    project,

                    data

                )


                print(
                    "production imported:",
                    len(imported)
                )



    db.close()



if __name__=="__main__":

    run()
