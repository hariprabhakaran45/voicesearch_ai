# ============================================================
# Yuganchin Voice Search AI — RunPod Serverless Handler
# Whisper (English + Tamil) + Qwen3 (Grocery Parser)
# ============================================================

import runpod
import base64
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

QWEN_MODEL_PATH = os.getenv(
    "QWEN_MODEL_PATH",
    "/app/models/Qwen3-1.7B-Q4_K_M.gguf",
)


# ============================================================
# 1. Load Whisper (Speech-to-Text for English + Tamil)
# ============================================================

print("=" * 60, flush=True)
print("Loading Whisper model (Speech-to-Text)...", flush=True)

import torch
from faster_whisper import WhisperModel

_device = "cuda" if torch.cuda.is_available() else "cpu"
_compute_type = "float16" if torch.cuda.is_available() else "int8"

_whisper_model = WhisperModel(
    "small",
    device=_device,
    compute_type=_compute_type,
)

print(f"Whisper ready on {_device}.", flush=True)
print("=" * 60, flush=True)


# ============================================================
# 2. Load Qwen3-1.7B Grocery Parser
# ============================================================

print("Loading Qwen3-1.7B grocery parser...", flush=True)

from llama_cpp import Llama

_n_gpu_layers = -1 if torch.cuda.is_available() else 0

_llm = Llama(
    model_path=QWEN_MODEL_PATH,
    n_ctx=4096,
    n_gpu_layers=_n_gpu_layers,
    n_threads=4,
    n_batch=128,
    verbose=False,
    seed=42,
)

print("Qwen3-1.7B grocery parser ready.", flush=True)
print("=" * 60, flush=True)


# ============================================================
# 3. Initialize GroceryParser
# ============================================================

from grocery_parser import GroceryParser

_grocery_parser = GroceryParser(llm=_llm)

print("GroceryParser initialized successfully.", flush=True)
print("=" * 60, flush=True)


# ============================================================
# Helper: Transcribe with Whisper
# ============================================================

def _transcribe(wav_path: str) -> str:
    segments, info = _whisper_model.transcribe(wav_path, beam_size=5)
    print(
        f"Detected language '{info.language}' "
        f"with probability {info.language_probability:.2f}",
        flush=True,
    )
    text = " ".join([segment.text for segment in segments])
    return text.strip()


# ============================================================
# RunPod Handler Function
# ============================================================

def handler(job: dict) -> dict:
    wav_path = None

    try:
        job_input = job.get("input", {})
        audio_b64 = job_input.get("audio_b64", "")

        if not audio_b64:
            return {"error": "audio_b64 is required"}

        try:
            wav_bytes = base64.b64decode(audio_b64)
        except Exception as decode_error:
            return {"error": f"Invalid base64 audio: {decode_error}"}

        if not wav_bytes:
            return {"error": "audio_b64 decoded to empty bytes"}

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(wav_bytes)
            wav_path = tmp.name

        print(f"Audio received: {len(wav_bytes)} bytes", flush=True)

        # 1. Speech to Text (Whisper — auto-detect language)
        print("Starting Whisper...", flush=True)
        transcript = _transcribe(wav_path)
        print(f"TRANSCRIPT: {transcript}", flush=True)

        if not transcript:
            return {"error": "No speech detected. Please try again."}

        # 2. Grocery Parsing (Qwen3 — already multilingual)
        print("Starting Qwen3 grocery parser...", flush=True)
        parsed_result = _grocery_parser.parse(transcript)
        print("Qwen3 parsing completed.", flush=True)

        if not isinstance(parsed_result, dict):
            return {"error": "Grocery parser returned invalid result"}

        items = parsed_result.get("items")
        if not isinstance(items, list):
            return {"error": "Grocery parser did not return items list"}

        result = {
            "transcript": transcript,
            "items": items,
        }
        print(f"VOICE SEARCH SUCCESS: {result}", flush=True)
        return result

    except Exception as error:
        print(f"HANDLER ERROR: {repr(error)}", flush=True)
        traceback.print_exc()
        return {"error": str(error)}

    finally:
        if wav_path and os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass


# ============================================================
# Start RunPod Serverless Loop
# ============================================================

if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})