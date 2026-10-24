# ============================================================
# Yuganchin Voice Search AI — RunPod Serverless GPU Worker
# Whisper (English + Tamil) + Qwen3 (Grocery Parser)
#
# NOTE: This Dockerfile is kept for reference / future Docker-based
# deployments. Current production uses RunPod Pre-built Template +
# Network Volume, so this Dockerfile is NOT actively used.
# ============================================================

FROM pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 1. System dependencies (ffmpeg required for Whisper)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    ffmpeg \
    libsndfile1 \
    libsndfile1-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Upgrade pip and build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel Cython

# 3. Python dependencies (Whisper + llama-cpp + runpod)
COPY runpod_worker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 4. llama-cpp-python pre-built CUDA 12.1 wheel
RUN pip install --no-cache-dir llama-cpp-python \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121

# 5. Copy application files
COPY runpod_worker/handler.py /app/handler.py
COPY runpod_worker/grocery_parser.py /app/grocery_parser.py

# 6. Model paths — from Network Volume at runtime
#    (No model files baked into image; mounted at /runpod-volume/)
ENV QWEN_MODEL_PATH=/runpod-volume/Qwen3-1.7B-Q4_K_M.gguf
ENV WHISPER_MODEL_DIR=/runpod-volume/whisper

# 7. Create mount point for network volume
RUN mkdir -p /runpod-volume

# 8. Run handler
CMD ["python3", "-u", "/app/handler.py"]