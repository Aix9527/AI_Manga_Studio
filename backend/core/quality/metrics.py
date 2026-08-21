from pathlib import Path
import cv2
import numpy as np



class VideoMetrics:



    def calculate(
        self,
        video_path
    ):

        path=Path(video_path)


        if not path.exists():

            return {

                "error":
                "missing"

            }


        cap=cv2.VideoCapture(
            str(path)
        )


        frames=[]


        while len(frames)<8:


            ok,frame=cap.read()


            if not ok:
                break


            frames.append(
                frame
            )


        cap.release()



        if len(frames)<2:

            return {

                "static":True,

                "motion_cv":1,

                "ssim":0

            }



        diffs=[]


        for i in range(
            1,
            len(frames)
        ):


            diff=cv2.absdiff(

                frames[i-1],

                frames[i]

            )


            diffs.append(

                np.mean(diff)/255

            )



        motion=float(
            np.mean(diffs)
        )


        return {

            "motion_cv":
            motion,


            "ssim":
            max(
                0,
                1-motion
            ),


            "mosaic":
            False,


            "static":
            motion < 0.001

        }
