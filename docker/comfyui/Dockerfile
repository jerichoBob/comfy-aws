FROM python:3.11-slim

WORKDIR /app

# Download ComfyUI via Python script (HTTPS only — no apt-get, no git)
COPY download_comfyui.py /tmp/download_comfyui.py
RUN python /tmp/download_comfyui.py && rm /tmp/download_comfyui.py

# CPU-only torch to keep image small for local dev
RUN pip install --no-cache-dir \
    torch torchvision torchaudio \
    --extra-index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt

# Custom nodes
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes.git \
    /app/custom_nodes/ComfyUI_Comfyroll_CustomNodes

# Create model directories
RUN mkdir -p models/checkpoints models/loras models/vae output

EXPOSE 8188

# --cpu flag disables GPU; override CMD in docker-compose.gpu.yml to remove it
CMD ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188", "--cpu"]
