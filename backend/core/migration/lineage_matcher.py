from pathlib import Path



IMAGE_EXT = {
    ".png",
    ".jpg",
    ".jpeg"
}


VIDEO_EXT = {
    ".mp4",
    ".mov"
}



class LineageMatcher:


    def extract_shot_key(
        self,
        path:Path
    ):

        parts = path.parts


        for p in parts:

            low=p.lower()


            if (
                low.startswith("shot")
                or
                low.startswith("gx")
            ):

                return low



        return path.stem.lower()



    def pair(
        self,
        versions
    ):


        images=[]

        videos=[]


        for v in versions:


            p=Path(
                v.path
            )


            if p.suffix.lower() in IMAGE_EXT:

                images.append(v)


            elif p.suffix.lower() in VIDEO_EXT:

                videos.append(v)



        result=[]


        for img in images:


            img_key=self.extract_shot_key(
                Path(img.path)
            )


            best=None


            for video in videos:


                video_key=self.extract_shot_key(
                    Path(video.path)
                )


                if img_key == video_key:

                    best=video

                    break



            if best:


                result.append(
                    (
                        img,
                        best
                    )
                )



        return result
