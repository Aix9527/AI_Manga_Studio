import TaskQueue
from "./components/TaskQueue";

import QCPanel
from "./components/QCPanel";


import DefectPanel
from "./components/DefectPanel";



export default function ReviewCenter(){


return (

<div>

<h1>
任务与审片中心
</h1>


<TaskQueue/>


<QCPanel/>


<DefectPanel/>


</div>

)

}
