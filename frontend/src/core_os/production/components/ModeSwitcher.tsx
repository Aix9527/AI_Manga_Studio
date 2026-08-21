import type {
ProductionMode
}
from "../types";


interface Props{

mode:ProductionMode;

onChange:
(
m:ProductionMode
)=>void;

}


export default function ModeSwitcher(
{
mode,
onChange
}:Props
){


return (

<div className="mode-switcher">


<button

className={
mode==="one_click"
?"active":""
}

onClick={()=>onChange("one_click")}

>

一键成片

</button>


<button

className={
mode==="professional"
?"active":""
}

onClick={()=>onChange("professional")}

>

专业精修

</button>


</div>

)

}
