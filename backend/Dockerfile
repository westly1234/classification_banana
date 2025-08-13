# syntax=docker/dockerfile:1.6
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

# OS 패키지 (자주 안 바뀌는 레이어)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libgl1 libglib2.0-0 ca-certificates fonts-nanum \
 && rm -rf /var/lib/apt/lists/*

# 1) requirements만 먼저 복사 → pip install (레이어 캐시 유지)
# rootDir=backend 이므로 컨텍스트 루트에 requirements.txt가 바로 존재함
COPY requirements.txt /tmp/requirements.txt

# BuildKit pip 캐시 (설치 속도↑, 재빌드 시 캐시 재사용)
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip setuptools wheel && \
    pip install --prefer-binary -r /tmp/requirements.txt

# 2) 앱 소스 마지막에 복사 (이 레이어만 자주 invalid)
COPY . /app/

# 런타임 준비
RUN mkdir -p /app/results

# Render는 동적으로 PORT를 주입하므로 반드시 $PORT를 따르도록
# (로컬에선 10000으로 기본값)
ENV PORT=10000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
