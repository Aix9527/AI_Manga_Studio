export interface Clip {


id:string;


assetPath:string;


start:number;


duration:number;


}



export interface Track {


id:string;


type:
"video"
|
"audio"
|
"subtitle";


clips:Clip[];

}
