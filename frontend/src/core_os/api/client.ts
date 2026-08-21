const API_BASE =
    "http://127.0.0.1:8000/api/core";


async function request<T>(
    url:string,
    options?:RequestInit
):Promise<T>{

    const res =
        await fetch(
            API_BASE + url,
            {
                headers:{
                    "Content-Type":
                    "application/json"
                },
                ...options
            }
        );


    if(!res.ok){

        throw new Error(
            await res.text()
        );

    }


    return res.json();

}


export const coreApi = {


    projects(){

        return request<any[]>(
            "/projects"
        );

    },


    shots(){

        return request<any[]>(
            "/shots"
        );

    },


    assets(){

        return request<any[]>(
            "/assets"
        );

    },


    assetDetail(
        id:string
    ){

        return request<any>(
            `/assets/${id}`
        );

    },


    assetLineage(
        id:string
    ){

        return request<any>(
            `/assets/${id}/lineage`
        );

    },


    workspace(
        id:string
    ){

        return request<any>(
            `/workspace/${id}`
        );

    },


    productionPlan(
        body:any
    ){

        return request<any>(
            "/production/plan",
            {
                method:"POST",

                body:
                JSON.stringify(body)
            }
        );

    },


    tasks(){

        return request<any[]>(
            "/tasks"
        );

    },


    mediaTracks(){

        return request<any[]>(
            "/media/tracks"
        ).catch(()=>[] as any[]);

    },


    mediaClips(){

        return request<any[]>(
            "/media/clips"
        ).catch(()=>[] as any[]);

    },


    mediaExport(
        body:any
    ){

        return request<any>(
            "/media/export",
            {
                method:"POST",

                body:
                JSON.stringify(body)
            }
        );

    },


    mediaReport(
        projectId:string
    ){

        return request<any>(
            `/media/report/${projectId}`
        );

    }

};
