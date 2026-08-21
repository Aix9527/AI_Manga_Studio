from dataclasses import dataclass



@dataclass
class SkillSchema:


    name:str

    role:str


    input_schema:dict


    output_schema:dict


    read_domains:list


    write_domains:list


    tools:list


    allow_cloud:bool=False
