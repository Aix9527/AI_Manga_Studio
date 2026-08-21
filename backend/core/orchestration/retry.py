MAX_RETRY=2



class RetryPolicy:



    def can_retry(
        self,
        failure_count
    ):


        return failure_count < MAX_RETRY



    def next_state(
        self,
        failure_count
    ):


        if self.can_retry(
            failure_count
        ):

            return "retry"



        return "manual_review"
