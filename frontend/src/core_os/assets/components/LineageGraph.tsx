import {

useEffect,

useState

}

from "react";



export default function LineageGraph(
{
assetId
}:{
assetId:string
}

){


const [

edges,

setEdges

]=useState<any[]>([]);



useEffect(()=>{


fetch(

`http://127.0.0.1:8000/api/core/assets/${assetId}/lineage`

)

.then(

r=>r.json()

)

.then(
d=>setEdges(
d.edges||[]
)
);

},[assetId]);



return (

<div>


<h3>
血缘关系
</h3>


{

edges.map(
e=>

<div

key={
e.parent+e.child
}

>

{e.parent}

↓

{e.relation}

↓

{e.child}


</div>

)
}


</div>

)

}
