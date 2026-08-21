import {
useEffect,
useState
}
from "react";

import {
coreApi
}
from "../api/client";


export default function ProjectCenter(){


const [projects,setProjects]=useState<any[]>([]);


useEffect(()=>{

coreApi.projects()
.then(setProjects);


},[]);



return (

<div>

<h1>
项目中心
</h1>


{
projects.map(
p=>

<div key={p.id}>

{p.name}

</div>

)
}


</div>

)

}
