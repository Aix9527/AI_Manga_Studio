import {

useEffect,

useState

}

from "react";



export default function QCPanel(){


const [

qc,

setQc

]=useState<any[]>([]);



useEffect(()=>{


fetch(
"http://127.0.0.1:8000/api/core/review/quality"
)

.then(
r=>r.json()
)

.then(
setQc
);


},[]);



return (

<div>

<h2>
质量审片
</h2>


{

qc.map(

q=>

<div key={q.id}>

{q.shot_id}

:

{q.score}

:

{q.result}

</div>

)

}

</div>

)

}
