from .schema import SkillSchema



DEFAULT_AGENT_SKILLS=[


SkillSchema(

name="director",

role="导演",

input_schema={

"shot":"Shot",

"character":"Character"

},

output_schema={

"prompt_recipe":"PromptRecipe"

},

read_domains=[

"shot",

"character",

"world"

],

write_domains=[

"prompt_recipe"

],

tools=[

"prompt_compiler"

]

),



SkillSchema(

name="quality",

role="质检",

input_schema={

"asset":"Asset"

},

output_schema={

"quality":"Evaluation"

},

read_domains=[

"asset"

],

write_domains=[

"quality"

],

tools=[

"quality_gate"

]

)

]
