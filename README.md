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

The grocery parser logic is defined in a staged design in `grocery_parser.py`, but the file currently contains a large commented-out prototype, so the live parser behavior depends on the implementation used in the active environment.

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

How to install it:
1. Download or obtain the `.nemo` checkpoint file for the Tamil IndicConformer model.
2. Place it inside the project folder under:
```bash
/home/hari/voicesearch_ai/models/
```
3. Make sure the file name matches the path in `speech_service.py`:
```bash
indicconformer_stt_ta_hybrid_rnnt_large.nemo
```
4. If your download uses a different file name, update the `MODEL_PATH` in `speech_service.py`.

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

How to install it:
1. Download the Qwen3-1.7B Q4 GGUF model file.
2. Place it inside:
```bash
/home/hari/voicesearch_ai/models/
```
3. Ensure the file name matches the expected path in `grocery_parser.py`.

Example:
```python
MODEL_PATH = (
    "/home/hari/voicesearch_ai/models/"
    "Qwen3-1.7B-Q4_K_M.gguf"
)
```

Important note:
- The project currently contains the parser logic as a commented-out prototype, so the active runtime may depend on the exact model file and implementation available in your local environment.
- If the model files are missing, the app will fail when the model loader is invoked.

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
