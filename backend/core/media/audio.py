from ..domain.ids import create_id



class VoiceService:



    def synthesize(
        self,
        text,
        voice_profile,
        emotion="neutral"
    ):


        return {


            "audio_id":
            create_id(
                "voice"
            ),


            "text":
            text,


            "voice":
            voice_profile,


            "emotion":
            emotion,


            "provider":
            "cosyvoice"

        }
