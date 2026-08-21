import {
useState
}
from "react";


import {
coreApi
}
from "../../api/client";



export default function OneClickPanel(){


const [
result,
setResult
]=useState<any>();



async function start(){


const data =
await coreApi.productionPlan({

project_id:"",

template:
"anime_serial"

});


setResult(data);


}



return (

<div>


<h2>
一键成片
</h2>


<button
onClick={start}
>

生成生产计划

</button>



{
result &&

<pre>

{
JSON.stringify(
result,
null,
2
)
}

</pre>

}



</div>

)

}
