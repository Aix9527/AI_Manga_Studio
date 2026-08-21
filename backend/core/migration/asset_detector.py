from pathlib import Path



MEDIA_EXTENSIONS={

    ".png",
    ".jpg",
    ".jpeg",
    ".mp4",
    ".mov",
    ".json"

}



class AssetDetector:


    def scan(
        self,
        project_path:Path
    ):


        results=[]


        for file in project_path.rglob("*"):


            if not file.is_file():

                continue


            if file.suffix.lower() in MEDIA_EXTENSIONS:

                results.append(file)



        return results
