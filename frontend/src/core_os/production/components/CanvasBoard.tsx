import {

ReactFlow,

Background,

Controls,

Node

}

from "@xyflow/react";


import {

useMemo

}

from "react";


import {

useProduction

}

from "../context/ProductionContext";



import "@xyflow/react/dist/style.css";



export default function CanvasBoard(){


const {
selectedShot,
selectShot
}=useProduction();



const nodes:Node[]=
useMemo(

()=>[

{

id:"gx001",

position:{
x:100,
y:100
},

data:{
label:"gx001"
}


},

{

id:"gx002",

position:{
x:300,
y:200
},

data:{
label:"gx002"
}

}

]
,[]);



return (

<div
style={{
height:500
}}
>


<ReactFlow

nodes={nodes}

edges={[]}

onNodeClick={
(_,node)=>{

selectShot({

id:node.id,

name:String(
node.data.label
),

status:"imported"

})

}

}

/>


<Background/>

<Controls/>


</div>

)

}
