export type ProductionMode =
    | "one_click"
    | "professional";


export type ShotStatus =
    | "draft"
    | "imported"
    | "generating"
    | "passed"
    | "approved";


export interface Shot {


    id:string;


    name:string;


    status:ShotStatus;


    duration?:number;


    camera?:string;


    motion?:string;

}



export interface CanvasNode {


    id:string;


    type:
    | "shot"
    | "character"
    | "scene"
    | "asset";


    title:string;


    x:number;


    y:number;

}
