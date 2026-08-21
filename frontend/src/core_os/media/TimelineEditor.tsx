import React from "react";


export interface TimelineClip {

    id:string;

    name:string;

    type:string;

    start:number;

    duration:number;

    path?:string;

}


export interface TimelineTrack {

    id:string;

    name:string;

    type:string;

    clips:TimelineClip[];

}



interface Props {

    tracks:TimelineTrack[];

    onSelectClip?:(clip:TimelineClip)=>void;

}



export default function TimelineEditor(
{
    tracks,
    onSelectClip
}:Props
){


    return (

        <div className="timeline-editor">

            <h2>
                Timeline
            </h2>


            {
                tracks.map(track=>(

                    <div
                        key={track.id}
                        className="timeline-track"
                    >

                        <div className="track-title">

                            {track.name}

                        </div>


                        <div className="track-clips">


                            {
                                track.clips.map(
                                    clip=>(


                                    <button

                                        key={clip.id}

                                        className="timeline-clip"

                                        style={{

                                            marginLeft:
                                            `${clip.start * 20}px`,

                                            width:
                                            `${clip.duration * 20}px`

                                        }}

                                        onClick={()=>{

                                            onSelectClip?.(
                                                clip
                                            );

                                        }}

                                    >

                                        <span>
                                            {clip.name}
                                        </span>


                                        <small>

                                            {clip.type}

                                        </small>


                                    </button>


                                    )

                                )

                            }


                        </div>


                    </div>


                ))

            }


        </div>

    )

}
