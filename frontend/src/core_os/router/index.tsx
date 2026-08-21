import {
createBrowserRouter
}
from "react-router-dom";


import AppShell
from "../layout/AppShell";


import ProjectCenter
from "../pages/ProjectCenter";


import CreativeStudio
from "../pages/CreativeStudio";


import ProductionStudio
from "../pages/ProductionStudio";


import AssetBrowser
from "../pages/AssetBrowser";


import ReviewCenter
from "../pages/ReviewCenter";


import ExportCenter
from "../pages/ExportCenter";


import Settings
from "../pages/Settings";



export const router=createBrowserRouter([

{

path:"/os",

element:<AppShell/>,

children:[


{
path:"projects",
element:<ProjectCenter/>
},


{
path:"creative",
element:<CreativeStudio/>
},


{
path:"production",
element:<ProductionStudio/>
},


{
path:"assets",
element:<AssetBrowser/>
},


{
path:"review",
element:<ReviewCenter/>
},


{
path:"export",
element:<ExportCenter/>
},


{
path:"settings",
element:<Settings/>
}

]

}

]);
