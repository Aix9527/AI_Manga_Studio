import json



class StructuredDiffEngine:



    def create_update_diff(
        self,
        old:dict,
        new:dict
    ):


        diff={}



        keys=set(
            old.keys()
        ) | set(
            new.keys()
        )


        for key in keys:


            old_value=old.get(
                key
            )


            new_value=new.get(
                key
            )


            if old_value != new_value:


                diff[key]={
                    "old":
                    old_value,

                    "new":
                    new_value
                }


        return diff




    def serialize(
        self,
        diff
    ):

        return json.dumps(
            diff,
            ensure_ascii=False
        )
