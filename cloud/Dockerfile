# Build from the project root: docker build -f cloud/Dockerfile -t YOUR_IMAGE:runpod-preview .
FROM node:22-bookworm-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 IMAGEMAESTRO_CLOUD_REQUIRED=1 SERVER_NAME=0.0.0.0 SERVER_PORT=8080
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 libsndfile1 libportaudio2 espeak-ng git build-essential && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/imagemaestro
COPY requirements*.txt constraints.txt ./
RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install torch==2.9.1 torchvision==0.24.1 torchaudio==2.9.1 --index-url https://download.pytorch.org/whl/cu128
RUN python -m pip install -c constraints.txt -r requirements-cuda.txt
COPY app ./app
COPY cloud ./cloud
COPY --from=ui /ui/dist ./ui/dist
RUN useradd --create-home --uid 1000 maestro && chown -R maestro:maestro /opt/imagemaestro
EXPOSE 8080
# Runpod volumes are commonly root-owned. Entrypoint prepares only its own subdirectory,
# then permanently drops privileges before importing any model/application code.
ENTRYPOINT ["python", "/opt/imagemaestro/cloud/entrypoint.py"]
