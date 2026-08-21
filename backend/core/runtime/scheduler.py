import threading



class VRAMScheduler:


    def __init__(
        self,
        total_gb=16
    ):

        self.total=total_gb

        self.lock=threading.Lock()


    def acquire(
        self,
        required
    ):


        if required > self.total:

            return False



        return self.lock.acquire(
            blocking=False
        )



    def release(
        self
    ):


        if self.lock.locked():

            self.lock.release()



scheduler=VRAMScheduler()
