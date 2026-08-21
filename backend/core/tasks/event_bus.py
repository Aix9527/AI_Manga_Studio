import asyncio



class EventBus:


    def __init__(self):

        self.events=[]



    def publish(
        self,
        event_type,
        payload
    ):

        self.events.append(

            {
                "type":event_type,

                "payload":payload
            }

        )



    async def stream(self):

        index=0


        while True:

            while index < len(self.events):

                yield self.events[index]

                index+=1


            await asyncio.sleep(
                1
            )



event_bus=EventBus()
