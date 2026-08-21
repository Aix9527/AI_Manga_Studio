import type {
Track
}
from "../timeline";


const tracks:Track[]=[


{

id:"video",

type:"video",

clips:[

{

id:"gx001",

assetPath:"gx001.mp4",

start:0,

duration:5

}

]

},


{

id:"audio",

type:"audio",

clips:[]

},


{

id:"subtitle",

type:"subtitle",

clips:[]

}


];



export default function Timeline(){


return (

<div className="timeline">


<h3>
Timeline
</h3>


{
tracks.map(
t=>

<div key={t.id}>

{t.type}

:

{
t.clips.length
}

clips

</div>

)
}


</div>

)

}
