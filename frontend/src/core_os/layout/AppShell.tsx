import {
    NavLink,
    Outlet
}
from "react-router-dom";

import "../styles.css";


const menus=[

{
label:"项目中心",
path:"/os/projects"
},

{
label:"创作开发",
path:"/os/creative"
},

{
label:"制作工作台",
path:"/os/production"
},

{
label:"素材资产",
path:"/os/assets"
},

{
label:"任务审片",
path:"/os/review"
},

{
label:"成片导出",
path:"/os/export"
},

{
label:"系统设置",
path:"/os/settings"
}

];


export default function AppShell(){


return (

<div className="core-shell">


<aside>


<h2>
AI Manga Studio
</h2>


{
menus.map(
m=>

<NavLink
key={m.path}
to={m.path}
>

{m.label}

</NavLink>

)
}


</aside>


<main>

<Outlet/>

</main>


</div>

)

}
