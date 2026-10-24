# Yuganchin Voice Search AI — RunPod Serverless Worker

This folder contains everything needed to run both **IndicConformer Tamil ASR** and **Qwen3-1.7B Grocery Parser** on a single RunPod Serverless GPU container.

---

## 📁 File Structure

```
voicesearch_ai/
├── runpod_worker/
│   ├── handler.py          # RunPod Serverless worker entry point
│   ├── Dockerfile          # CUDA + NeMo + llama.cpp container
│   ├── requirements.txt    # Python dependencies for the worker
│   ├── test_local.py       # Test the worker locally on Ubuntu without spending credits
│   └── README.md           # Instructions
├── grocery_parser.py       # Updated parser logic (supports pre-loaded LLM)
├── speech_service.py       # Updated speech service (supports GPU & lazy loading)
├── app.py                  # FastAPI gateway (auto-detects RunPod vs local execution)
└── .env                    # Environment variables (API keys & RunPod endpoint)
```

---

## 🧪 Step 1: Test Locally in VS Code (Ubuntu) — No Credits Needed

Before deploying to RunPod or spending any money, you can test the handler on your Ubuntu machine with your existing models:

```bash
# In your Ubuntu VS Code terminal:
cd ~/voicesearch_ai/runpod_worker

# Run local test using any sample 16kHz WAV file:
python3 test_local.py /path/to/sample.wav
```

You should see:
1. Both models load once into memory.
2. Speech transcription runs.
3. Qwen3 grocery parsing runs.
4. Output prints:
   ```json
   {
     "transcript": "...",
     "items": [
       { "name": "...", "quantity": 500, "unit": "g" }
     ]
   }
   ```

---

## 🐳 Step 2: Build & Push Docker Image (When Ready for RunPod)

When you're ready to deploy to RunPod:

1. Log in to Docker Hub:
   ```bash
   docker login
   ```

2. Build the Docker image:
   ```bash
   cd ~/voicesearch_ai/runpod_worker
   cp ../grocery_parser.py .

   # Build for linux/amd64:
   docker build -t yourdockerusername/yuganchin-voicesearch:latest .
   ```

3. Push to Docker Hub:
   ```bash
   docker push yourdockerusername/yuganchin-voicesearch:latest
   ```

---

## ☁️ Step 3: Configure RunPod Serverless Endpoint

1. Go to [RunPod Serverless Console](https://www.runpod.io/console/serverless).
2. Click **New Endpoint**.
3. Fill in:
   - **Endpoint Name**: `yuganchin-voicesearch`
   - **Container Image**: `yourdockerusername/yuganchin-voicesearch:latest`
   - **GPU Type**: 16 GB or 24 GB GPU (e.g. RTX 3090, RTX 4090, or L4)
   - **Active Workers (Min)**: `0` (scales to 0 when idle so you pay $0!)
   - **Max Workers**: `3` (adjust based on expected traffic)
   - **Idle Timeout**: `5` seconds
   - **Container Disk**: `20 GB`
4. Under **Environment Variables**:
   - `INDICCONFORMER_MODEL_PATH`: `/runpod-volume/indicconformer_stt_ta_hybrid_rnnt_large.nemo` (or baked path)
   - `QWEN_MODEL_PATH`: `/runpod-volume/Qwen3-1.7B-Q4_K_M.gguf` (or baked path)
5. Click **Create Endpoint**.
6. Copy your **Endpoint ID** (e.g. `abc123xyz`).

---

## 🔌 Step 4: Connect FastAPI `app.py` to RunPod

In your Ubuntu `voicesearch_ai/.env`:

```env
VOICE_SEARCH_API_KEY=chintam-yuganchinstore123456

# Add your RunPod credentials here:
RUNPOD_API_KEY=your_runpod_api_key_here
RUNPOD_ENDPOINT_ID=your_runpod_endpoint_id_here
```

When you start FastAPI:
```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

`app.py` will display:
```
[VoiceSearch] Mode: RUNPOD SERVERLESS (Endpoint: your_runpod_endpoint_id_here)
```

Now, when a customer uses voice search in the mobile app:
1. `app.py` receives the audio upload.
2. Converts it to 16kHz mono WAV.
3. Sends it to RunPod GPU Serverless for instant transcription + parsing.
4. Returns the structured grocery list back to the mobile app in milliseconds!
