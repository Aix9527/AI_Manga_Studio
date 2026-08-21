import json

from ..domain.ids import create_id

from ..storage.runtime_models import (
    AgentSkillRecord
)



DEFAULT_SKILLS=[


{

"name":"screenwriter",

"role":"编剧",

"allow_cloud":0

},


{

"name":"director",

"role":"导演",

"allow_cloud":0

},


{

"name":"quality",

"role":"质检",

"allow_cloud":0

}


]



def install_default_skills(db):


    for item in DEFAULT_SKILLS:


        exists=(

            db.query(
                AgentSkillRecord
            )

            .filter_by(
                name=item["name"]
            )

            .first()

        )


        if exists:

            continue



        db.add(

            AgentSkillRecord(

                id=create_id(
                    "skill"
                ),

                name=item["name"],

                role=item["role"],

                input_schema="{}",

                output_schema="{}",

                read_domains="*",

                write_domains="",

                allow_cloud=item["allow_cloud"]

            )

        )


    db.commit()
