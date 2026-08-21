import {
ReactFlow
}
from "@xyflow/react";


import {
useEffect,
useState
}
from "react";



export default function CanvasWorkspace(){

const [
nodes,
setNodes
]=useState<any[]>([]);



useEffect(()=>{


fetch(

"http://127.0.0.1:8000/api/core/canvas/gx"

)

.then(
r=>r.json()
)

.then(
setNodes
);


},[]);



return (

<div
style={{
height:600
}}
>

<ReactFlow

nodes={nodes.map(n=>({

id:n.id,

position:{
x:100,
y:100
},

data:{
label:n.title
}

}))}

edges={[]}

/>

</div>

)

}
