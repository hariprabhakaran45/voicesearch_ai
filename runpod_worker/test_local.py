"""
Test the RunPod handler locally before deploying.
Usage:
    python3 test_local.py [path_to_audio_file.wav]
"""

import sys
import os
import base64
import json

# Add parent directory so grocery_parser can be found
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set environment variables for model paths if needed
# os.environ["INDICCONFORMER_MODEL_PATH"] = "/home/hari/voicesearch_ai/models/indicconformer_stt_ta_hybrid_rnnt_large.nemo"
# os.environ["QWEN_MODEL_PATH"] = "/home/hari/voicesearch_ai/models/Qwen3-1.7B-Q4_K_M.gguf"

from handler import handler

def run_test(audio_file_path: str):
    print(f"Reading audio file: {audio_file_path}")
    with open(audio_file_path, "rb") as f:
        audio_bytes = f.read()

    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    print(f"Audio size: {len(audio_bytes)} bytes (base64 length: {len(audio_b64)})")

    job = {
        "id": "local_test_1",
        "input": {
            "audio_b64": audio_b64,
            "language_id": "ta"
        }
    }

    print("\nCalling handler...")
    response = handler(job)

    print("\n" + "=" * 50)
    print("HANDLER RESULT:")
    print(json.dumps(response, ensure_ascii=False, indent=2))
    print("=" * 50)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        wav_path = sys.argv[1]
    else:
        print("Please provide a path to a 16kHz mono WAV file to test:")
        print("Example: python3 test_local.py /path/to/sample.wav")
        sys.exit(1)

    run_test(wav_path)
