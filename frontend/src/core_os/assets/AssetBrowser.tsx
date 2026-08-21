import {

useEffect,

useState

}

from "react";


import {

coreApi

}

from "../api/client";


import VersionTree
from "./components/VersionTree";


import LineageGraph
from "./components/LineageGraph";



export default function AssetBrowser(){


const [

assets,

setAssets

]=useState<any[]>([]);



const [

selected,

setSelected

]=useState<any>();



useEffect(()=>{


coreApi.assets()

.then(
setAssets
);


},[]);



return (

<div>


<h1>
素材资产中心
</h1>


<div className="asset-layout">


<div>

{

assets.map(
a=>

<div

key={a.id}

onClick={()=>setSelected(a)}

className="asset-item"

>

{a.name}

</div>

)
}

</div>



<div>


{

selected &&

<>

<h3>

{selected.name}

</h3>


<VersionTree

versions={
selected.versions
}

/>


<LineageGraph

assetId={
selected.id
}

/>


</>

}


</div>


</div>


</div>

)

}
