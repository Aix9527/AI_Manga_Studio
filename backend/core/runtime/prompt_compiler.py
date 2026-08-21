class PromptCompiler:



    def compile(
        self,
        shot,
        character,
        world
    ):


        return {


        "prompt":

        f"""

World:
{world}


Character:
{character}


Shot:
{shot}


Generate cinematic result.

"""


        }
