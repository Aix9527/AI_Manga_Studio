from fastapi import APIRouter, UploadFile, File


from backend.core.storage.database import SessionLocal


from backend.core.creative.parser import NarrativeParser

from backend.core.creative.splitter import NarrativeSplitter

from backend.core.creative.importer import NarrativeImporter



router=APIRouter()



@router.post(
"/import"
)

async def import_story(

    project_id:str,

    file:UploadFile=File(...)

):


    content=await file.read()


    temp="temp_"+file.filename


    open(
        temp,
        "wb"
    ).write(
        content
    )



    parser=NarrativeParser()


    parsed=parser.parse_file(
        temp
    )


    episodes=NarrativeSplitter().split(
        parsed
    )



    db=SessionLocal()


    importer=NarrativeImporter(
        db
    )


    result=importer.import_story(

        project_id,

        file.filename,

        content,

        episodes

    )


    db.close()



    return {

        "import_id":
        result,

        "episodes":
        len(episodes)

    }
