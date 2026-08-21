import {

useEffect,

useState

}

from "react";


export default function TaskQueue(){


const [

tasks,

setTasks

]=useState<any[]>([]);



useEffect(()=>{


fetch(
"http://127.0.0.1:8000/api/core/tasks"
)

.then(
r=>r.json()
)

.then(
setTasks
);



const es=new EventSource(

"http://127.0.0.1:8000/api/core/tasks/stream"

);


es.onmessage=(e)=>{


console.log(
e.data
);


};


return ()=>es.close();



},[]);



async function control(
id:string,
action:string
){


await fetch(

`http://127.0.0.1:8000/api/core/tasks/${id}/${action}`,

{
method:"POST"
}

);


location.reload();

}



return (

<div>


<h2>
任务队列
</h2>


{
tasks.map(
t=>

<div key={t.id}>


<p>
{t.id}
</p>


<p>
P{t.priority}
</p>


<p>
{t.status}
</p>



<button
onClick={()=>
control(
t.id,
"pause"
)}
>
暂停
</button>


<button
onClick={()=>
control(
t.id,
"resume"
)}
>
恢复
</button>


<button
onClick={()=>
control(
t.id,
"retry"
)}
>
重试
</button>


<button
onClick={()=>
control(
t.id,
"cancel"
)}
>
取消
</button>



</div>

)
}


</div>

)

}
