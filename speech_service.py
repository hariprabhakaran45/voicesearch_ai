import torch
from nemo.collections.asr.models import EncDecHybridRNNTCTCBPEModel


MODEL_PATH = (
    "/home/hari/voicesearch_ai/models/"
    "indicconformer_stt_ta_hybrid_rnnt_large.nemo"
)


class TamilSpeechService:

    def __init__(self):
        print("Loading Tamil IndicConformer...")

        torch.set_num_threads(4)

        self.model = (
            EncDecHybridRNNTCTCBPEModel.restore_from(
                restore_path=MODEL_PATH,
                map_location=torch.device("cpu"),
            )
        )

        self.model.freeze()
        self.model.eval()

        # We selected CTC for our service
        self.model.cur_decoder = "ctc"

        print("Tamil IndicConformer ready.")


    def transcribe(self, audio_path: str) -> str:

        result = self.model.transcribe(
            [audio_path],
            batch_size=1,
            logprobs=False,
            language_id="ta",
        )

        # NeMo returns:
        # (['transcript'], ['transcript'])
        text = result[0][0]

        return text.strip()


speech_service = TamilSpeechService()
