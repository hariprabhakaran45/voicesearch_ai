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

# ──────────────────────────────────────────────────────────
# RUNTIME PATHS
# ──────────────────────────────────────────────────────────
QWEN_MODEL_DIR = "/app/models"
QWEN_MODEL_PATH = "/app/models/Qwen3-1.7B-Q4_K_M.gguf"
WHISPER_MODEL_DIR = "/app/models/whisper"

os.makedirs(QWEN_MODEL_DIR, exist_ok=True)
os.makedirs(WHISPER_MODEL_DIR, exist_ok=True)

# ============================================================
# 0. Download Qwen3 if not present
# ============================================================
if not os.path.exists(QWEN_MODEL_PATH):
    print("=" * 60, flush=True)
    print("Qwen3 model not found. Downloading from HuggingFace...", flush=True)
    print("=" * 60, flush=True)

    try:
        from huggingface_hub import hf_hub_download
        
        # VERIFIED REPO for Qwen3 GGUF
        downloaded_path = hf_hub_download(
            repo_id="bartowski/Qwen_Qwen3-1.7B-GGUF",
            filename="Qwen_Qwen3-1.7B-Q4_K_M.gguf",
            local_dir=QWEN_MODEL_DIR,
        )
        
        # Rename to our expected path
        if os.path.exists(downloaded_path) and downloaded_path != QWEN_MODEL_PATH:
            os.rename(downloaded_path, QWEN_MODEL_PATH)
            
        print("Qwen3 download complete.", flush=True)
    except Exception as e:
        print(f"FATAL: Qwen3 download failed: {e}", flush=True)
        raise e
else:
    print(f"Qwen3 already exists at {QWEN_MODEL_PATH}", flush=True)


# ============================================================
# 1. Load Whisper
# ============================================================
print("=" * 60, flush=True)
print("Loading Whisper (Speech-to-Text)...", flush=True)

import torch
from faster_whisper import WhisperModel

_device = "cuda" if torch.cuda.is_available() else "cpu"
_compute_type = "float16" if torch.cuda.is_available() else "int8"

_whisper_model = WhisperModel(
    "small",
    device=_device,
    compute_type=_compute_type,
    download_root=WHISPER_MODEL_DIR,
)

print(f"Whisper ready on {_device}.", flush=True)
print("=" * 60, flush=True)


# ============================================================
# 2. Load Qwen3
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
# Helper: Transcribe
# ============================================================
def _transcribe(wav_path: str) -> str:
    segments, info = _whisper_model.transcribe(wav_path, beam_size=5)
    print(f"Detected language '{info.language}' (prob {info.language_probability:.2f})", flush=True)
    return " ".join([s.text for s in segments]).strip()


# ============================================================
# Handler
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
        except Exception as e:
            return {"error": f"Invalid base64: {e}"}

        if not wav_bytes:
            return {"error": "Empty audio"}

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(wav_bytes)
            wav_path = tmp.name

        print(f"Audio received: {len(wav_bytes)} bytes", flush=True)

        transcript = _transcribe(wav_path)
        print(f"TRANSCRIPT: {transcript}", flush=True)

        if not transcript:
            return {"error": "No speech detected"}

        parsed = _grocery_parser.parse(transcript)
        print("Qwen3 parsing completed.", flush=True)

        if not isinstance(parsed, dict):
            return {"error": "Invalid parser result"}

        items = parsed.get("items")
        if not isinstance(items, list):
            return {"error": "No items list"}

        result = {"transcript": transcript, "items": items}
        print(f"SUCCESS: {result}", flush=True)
        return result

    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        traceback.print_exc()
        return {"error": str(e)}

    finally:
        if wav_path and os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})