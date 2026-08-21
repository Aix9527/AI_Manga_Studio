import React, {
useEffect,
useState
}
from "react";


import TimelineEditor,{
TimelineTrack,
TimelineClip
}
from "./TimelineEditor";



const API="/api/core";



interface ExportReport {

    export_id:string;

    video_sha256:string;

    resolution:string;

    qc_result:string;

    qc_score:number|null;

}



export default function ExportCenter(){


    const [tracks,setTracks]=useState<
        TimelineTrack[]
    >([]);


    const [
        selectedClip,
        setSelectedClip
    ]=useState<TimelineClip|null>(
        null
    );


    const [
        report,
        setReport
    ]=useState<ExportReport|null>(
        null
    );


    const [
        template,
        setTemplate
    ]=useState(
        "opening"
    );



    const projectId="gx";



    useEffect(()=>{


        fetch(
            `${API}/export/timeline/${projectId}`
        )
        .then(
            r=>r.json()
        )
        .then(
            setTracks
        );


    },[]);





    async function exportVideo(){


        const response =
        await fetch(
            `${API}/export/build`,
            {

                method:"POST",

                headers:{
                    "Content-Type":
                    "application/json"
                },


                body:JSON.stringify({

                    project_id:
                    projectId,


                    timeline:
                    tracks,


                    template,


                    resolution:
                    "1080x1920",


                    aspect_ratio:
                    "9:16",


                    output:
                    "outputs/final.mp4"

                })

            }
        );


        const data =
        await response.json();


        if(data.report){

            setReport(
                data.report
            );

        }

    }




    return (

        <div
            className="export-center"
        >

            <h1>
                Export Center
            </h1>



            <section>

                <label>
                    Opening / Ending Template
                </label>


                <select

                    value={template}

                    onChange={
                        e=>
                        setTemplate(
                            e.target.value
                        )
                    }

                >

                    <option value="opening">

                        Opening

                    </option>


                    <option value="ending">

                        Ending

                    </option>


                </select>


            </section>



            <TimelineEditor

                tracks={tracks}

                onSelectClip={
                    setSelectedClip
                }

            />



            {
                selectedClip &&

                <section>

                    <h3>
                        Inspector
                    </h3>


                    <p>
                        {selectedClip.name}
                    </p>


                    <p>
                        Start:
                        {selectedClip.start}s
                    </p>


                    <p>
                        Duration:
                        {selectedClip.duration}s
                    </p>


                </section>

            }



            <section>

                <h3>
                    Audio Preview
                </h3>


                <button>
                    Dialogue
                </button>


                <button>
                    Music
                </button>


                <button>
                    SFX
                </button>


            </section>




            <section>

                <h3>
                    Safe Crop Preview
                </h3>


                <p>
                    16:9 → 9:16
                    Character safe zone enabled
                </p>


            </section>




            <button

                onClick={
                    exportVideo
                }

            >

                Build Export Package

            </button>




            {
                report &&

                <section>

                    <h3>
                        Export Evidence
                    </h3>


                    <p>
                        ID:
                        {report.export_id}
                    </p>


                    <p>
                        SHA256:
                        {report.video_sha256}
                    </p>


                    <p>
                        Resolution:
                        {report.resolution}
                    </p>


                    <p>
                        QC:
                        {report.qc_result}

                        {" "}

                        {report.qc_score}

                    </p>


                </section>

            }


        </div>

    )

}
