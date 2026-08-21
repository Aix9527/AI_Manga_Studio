import {
createContext,
useContext,
useState
}
from "react";


import type {
Shot
}
from "../types";



interface Context {


selectedShot?:Shot;


selectShot:
(
shot:Shot
)=>void;

}



const ProductionContext=
createContext<Context|null>(
null
);



export function ProductionProvider(
{
children
}:any
){


const [
selectedShot,
setSelectedShot
]=useState<Shot>();


return (

<ProductionContext.Provider

value={{

selectedShot,

selectShot:
setSelectedShot

}}

>

{children}

</ProductionContext.Provider>

)

}



export function useProduction(){

const ctx=
useContext(
ProductionContext
);


if(!ctx)

throw new Error(
"ProductionContext missing"
);


return ctx;

}
