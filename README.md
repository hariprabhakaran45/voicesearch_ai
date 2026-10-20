# Yuganchin Voice Search AI

A FastAPI-based voice search service for grocery shopping workflows. The system captures user audio, converts it to a normalized WAV file, transcribes Tamil speech with NeMo ASR, and prepares the transcript for a grocery item parser. It includes request cancellation handling so that a client disconnect stops the in-flight processing cleanly.

## Project overview

This project is organized around a simple AI processing pipeline:

- `app.py` exposes the HTTP API and orchestrates the request lifecycle.
- `speech_service.py` loads the Tamil IndicConformer ASR model and transcribes audio.
- `ai_queue.py` serializes expensive AI work so only one request uses the model stack at a time.
- `grocery_parser.py` is the grocery parsing layer and is designed to interpret the transcript into structured shopping items.
- `.env` contains the API key used by the backend.
- `models/` is expected to hold the local model files used by the app.

## Current implementation status

The active backend code includes:

- health check endpoint
- authenticated audio upload endpoint
- audio validation and temporary file handling
- FFmpeg conversion to 16 kHz mono WAV
- queue-based AI access control
- client disconnect cancellation watcher
- Tamil speech transcription with NeMo

`grocery_parser.py` uses `llama.cpp` through `llama-cpp-python` to load the local Qwen GGUF model and parse the ASR transcript into grocery items.

## Core API

### Health check

Endpoint:
- `GET /health`

Response:
- service status
- speech model name
- parser model name

### Voice search

Endpoint:
- `POST /voice-search`

Headers:
- `API-Key: <secret-key>`

Form fields:
- `audio` multipart file upload



Expected behavior:
1. Validate the uploaded audio file.
2. Save the original file temporarily.
3. Convert to 16 kHz mono WAV with FFmpeg.
4. Put the request through the AI request queue.
5. Transcribe with the IndicConformer model.
6. Parse the transcript into grocery items.
7. Return a JSON payload with `status`, `transcript`, and `items`.

### Queue status

Endpoint:
- `GET /queue-status`

This returns queue state including active processing and waiting requests.

## Models used and why they are required

This project currently uses two main AI components:

### 1) IndicConformer Tamil ASR model

Model used in code:
- `IndicConformer Tamil`
- model file path in `speech_service.py`: `/home/hari/voicesearch_ai/models/indicconformer_stt_ta_hybrid_rnnt_large.nemo`

Why this model is used:
- It is a Tamil speech-to-text model designed for automatic speech recognition.
- It is appropriate for transcribing spoken Tamil and mixed Tamil/English style grocery requests.
- It works well for voice commands recorded by users on a phone or microphone.
- It is a NeMo model, which matches the project’s ASR implementation and runtime setup.

Download the checkpoint from the [AI4Bharat model page](https://huggingface.co/ai4bharat/indicconformer_stt_ta_hybrid_rnnt_large). From the project directory in Ubuntu/WSL, run:

```bash
python -m pip install -U "huggingface_hub[cli]"
mkdir -p models
hf download ai4bharat/indicconformer_stt_ta_hybrid_rnnt_large \
  indicconformer_stt_ta_hybrid_rnnt_large.nemo \
  --local-dir models
```

If Hugging Face requires authentication or model access, sign in with an account that has access, then retry:

```bash
hf auth login
```

The downloaded file should be at `models/indicconformer_stt_ta_hybrid_rnnt_large.nemo`. This matches the path configured in `speech_service.py` when the repository is at `/home/hari/voicesearch_ai`. If your project is in another location, update `MODEL_PATH` in that file.

Example:
```python
MODEL_PATH = (
    "/home/hari/voicesearch_ai/models/"
    "indicconformer_stt_ta_hybrid_rnnt_large.nemo"
)
```

### 2) Qwen3-1.7B parser model

The code references a parser model for grocery item extraction:
- `Qwen3-1.7B`
- model file path appears in `grocery_parser.py` as a GGUF file:
```text
/home/hari/voicesearch_ai/models/Qwen3-1.7B-Q4_K_M.gguf
```

Why this model is used:
- It is meant to convert the ASR transcript into structured grocery items.
- It helps interpret natural speech, quantities, product names, and search intents.
- It is useful for parsing spoken Tamil grocery commands into meaningful item lists.

Download the quantized GGUF file from the [official Qwen model page](https://huggingface.co/Qwen/Qwen3-1.7B-GGUF). From the project directory in Ubuntu/WSL, run:

```bash
python -m pip install -U "huggingface_hub[cli]"
mkdir -p models
hf download Qwen/Qwen3-1.7B-GGUF \
  Qwen3-1.7B-Q4_K_M.gguf \
  --local-dir models
```

The downloaded file should be at `models/Qwen3-1.7B-Q4_K_M.gguf`. This matches the path configured in `grocery_parser.py` when the repository is at `/home/hari/voicesearch_ai`. If your project is in another location, update `MODEL_PATH` in that file.

Example:
```python
MODEL_PATH = (
    "/home/hari/voicesearch_ai/models/"
    "Qwen3-1.7B-Q4_K_M.gguf"
)
```

Important:
- Model checkpoints are large and are intentionally excluded from Git. Download them separately on each development/deployment machine rather than committing them to the repository.
- Check each model page for its license and any access requirements before downloading or using it.
- The application cannot start successfully if a required model file is missing or the configured path is incorrect.

## Why it runs on Ubuntu only

This project is designed for the Ubuntu/WSL environment because the application expects Linux-style paths and a native Linux toolchain for the ML workflow. In particular:

- The speech model path is set to a Linux filesystem location under `/home/hari/voicesearch_ai/models/...`.
- The project assumes a Unix environment for Python virtual environments, shell scripts, and local model loading.
- The backend relies on FFmpeg and a Linux-compatible NeMo/PyTorch runtime stack.
- The project was built to run in WSL (Windows Subsystem for Linux), which provides the Ubuntu environment needed by the models and tools.

This is why Windows-native execution is not the intended runtime for the current setup. The application is optimized for Ubuntu or WSL, not for a standard Windows CMD/PowerShell workflow.

## How to open Ubuntu OS / WSL

If you are on Windows, open Ubuntu from the Start menu or run this in Command Prompt or PowerShell:

```bash
wsl
```

If Ubuntu is not installed yet, install it first:

```bash
wsl --install -d Ubuntu
```

Then, once inside Ubuntu, go to the project folder:

```bash
cd /home/hari/voicesearch_ai
```

If your project is in another WSL location, use:

```bash
cd /home/<your-username>/<your-project-folder>
```

For example:

```bash
cd /home/hari/voicesearch_ai
```

Then activate the environment and run the app:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

## Required environment

### Python
- Python 3.10+ recommended

### System dependency
- FFmpeg must be installed and available on PATH

Example Ubuntu installation:
```bash
sudo apt update
sudo apt install ffmpeg
```

## Setup

1. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure the API key:
Create a `.env` file in the project root with:
```bash
VOICE_SEARCH_API_KEY=your-long-random-secret-key
```

4. Place the required model files in `models/` and update the model paths in `speech_service.py` and `grocery_parser.py` if necessary.

5. Start the service:
```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```



## Notes

- The application is built around a single-server AI queue to avoid overlapping model inference.
- Request cancellation is handled by watching the HTTP disconnect state.
- The project appears to be a prototype or custom deployment for Tamil grocery voice search and may require model files and local path tuning for a production environment.
