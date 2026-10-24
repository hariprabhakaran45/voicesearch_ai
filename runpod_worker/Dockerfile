FROM pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git ffmpeg libsndfile1 libsndfile1-dev curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip setuptools wheel Cython

COPY runpod_worker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

RUN pip install --no-cache-dir llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121

COPY runpod_worker/handler.py /app/handler.py
COPY grocery_parser.py /app/grocery_parser.py

RUN mkdir -p /app/models
COPY models/Qwen3-1.7B-Q4_K_M.gguf /app/models/Qwen3-1.7B-Q4_K_M.gguf

ENV QWEN_MODEL_PATH=/app/models/Qwen3-1.7B-Q4_K_M.gguf

CMD ["python3", "-u", "/app/handler.py"]