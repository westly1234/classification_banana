# syntax=docker/dockerfile:1.6   # BuildKit 캐시 마운트 활성화
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

# OS 패키지 (변동 적은 레이어)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libgl1 libglib2.0-0 ca-certificates fonts-nanum \
 && rm -rf /var/lib/apt/lists/*

# 1) requirements만 먼저 복사 → pip install (레이어 캐시 유지)
#   rootDir=backend 이므로 컨텍스트에 requirements.txt가 바로 존재
COPY requirements.txt /tmp/requirements.txt

# BuildKit의 캐시 마운트로 pip wheel 캐시 재사용
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip setuptools wheel && \
    pip install --prefer-binary -r /tmp/requirements.txt

# 2) 앱 소스 마지막에 복사 (이 레이어만 자주 invalid)
COPY . /app/

# 런타임 준비
RUN mkdir -p /app/results

ENV PORT=10000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]