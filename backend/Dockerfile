# syntax=docker/dockerfile:1.6
FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu \
    YOLO_CONFIG_DIR=/tmp/Ultralytics

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libgl1 libglib2.0-0 ca-certificates fonts-nanum \
 && rm -rf /var/lib/apt/lists/*

# 1) requirements만 복사 → 설치 (레이어 캐시 포인트)
COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip setuptools wheel && \
    pip install --prefer-binary --no-input -r /tmp/requirements.txt

# 2) 앱 소스
COPY . /app/

RUN mkdir -p /app/results

ENV PORT=10000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --workers 1"]