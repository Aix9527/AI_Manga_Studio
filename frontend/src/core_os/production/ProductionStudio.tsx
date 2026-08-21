import {
useState
}
from "react";


import ModeSwitcher
from "./components/ModeSwitcher";


import OneClickPanel
from "./components/OneClickPanel";


import ProfessionalPanel
from "./components/ProfessionalPanel";


import {
ProductionProvider
}
from "./context/ProductionContext";


import type {
ProductionMode
}
from "./types";



export default function ProductionStudio(){


const [
mode,
setMode
]=useState<ProductionMode>(
"one_click"
);



return (

<ProductionProvider>

<div>


<h1>
制作工作台
</h1>



<ModeSwitcher

mode={mode}

onChange={setMode}

/>



{
mode==="one_click"

?

<OneClickPanel/>

:

<ProfessionalPanel/>

}



</div>

</ProductionProvider>

)

}
