import type {
AssetVersion
}
from "../types";



export default function VersionTree(
{
versions
}:{
versions:AssetVersion[]
}

){


return (

<div className="version-tree">


<h3>
版本树
</h3>


{

versions.map(

v=>

<div

key={v.id}

>

<p>

版本:
{v.id}

</p>


<p>

SHA256:

{v.sha256}

</p>


<p>

路径:

{v.path}

</p>



{

v.status==="frozen"

&&

<span>
❄ Frozen
</span>

}



</div>

)

}


</div>

)

}
