export interface AssetVersion{


id:string;

path:string;

sha256:string;

status?:
"created"
|
"approved"
|
"frozen";

}



export interface Asset{


id:string;

name:string;

type:string;

relative_path:string;

versions:
AssetVersion[];

}
