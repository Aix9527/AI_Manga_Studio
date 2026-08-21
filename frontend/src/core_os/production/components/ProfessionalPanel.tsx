import CanvasBoard
from "./CanvasBoard";


import ShotGrid
from "./ShotGrid";


import Inspector
from "./Inspector";


import Timeline
from "./Timeline";



export default function ProfessionalPanel(){


return (

<div className="professional-layout">


<div>

<CanvasBoard/>

</div>


<div>

<ShotGrid/>

</div>


<div>

<Inspector/>

</div>


<div>

<Timeline/>

</div>


</div>

)

}
