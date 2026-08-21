import {

useEffect,

useState

}

from "react";


import {

useProduction

}

from "../context/ProductionContext";


export default function Inspector(){


const {
selectedShot
}=useProduction();



const [
detail,
setDetail
]=useState<any>();



useEffect(()=>{


if(!selectedShot)

return;


fetch(

`http://127.0.0.1:8000/api/core/shots/${selectedShot.id}`

)

.then(
r=>r.json()
)

.then(
setDetail
);


},[selectedShot]);



return (

<div className="inspector">


<h3>
Inspector
</h3>



{
detail &&

<>

<p>
Shot:
{detail.shot.name}
</p>


<p>
Seed:
{detail.production.seed}
</p>


<p>
Motion:
{detail.production.motion_profile}
</p>


<p>
QC:
{detail.quality.score}
{detail.quality.result}
</p>


<p>
Prompt:
{detail.prompt.text}
</p>


</>

}


</div>

)

}
