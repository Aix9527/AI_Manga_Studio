import {

useEffect,

useState

}

from "react";


import {

coreApi

}

from "../../api/client";


import {

useProduction

}

from "../context/ProductionContext";



export default function ShotGrid(){


const [

shots,

setShots

]=useState<any[]>([]);



const {
selectedShot,
selectShot
}=useProduction();



useEffect(()=>{

coreApi.shots()
.then(
setShots
);

},[]);



return (

<div>


<h3>
镜头网格
</h3>



<div className="shot-grid">


{

shots.map(

s=>

<div

key={s.id}

className={

selectedShot?.id===s.id

?

"shot-card selected"

:

"shot-card"

}


onClick={()=>selectShot(s)}

>


<h4>

{s.name}

</h4>


<p>
{s.status}
</p>


</div>

)

}


</div>


</div>

)

}
