# syntax=docker/dockerfile:1.6
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    # 벨트+멜빵: requirements에도 있지만 환경변수로도 CPU 인덱스 지정
    PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu \
    # Ultralytics 경고 제거 (루트 홈 쓰기 불가하니 /tmp 사용)
    YOLO_CONFIG_DIR=/tmp/Ultralytics

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libgl1 libglib2.0-0 ca-certificates fonts-nanum \
 && rm -rf /var/lib/apt/lists/*

# 1) requirements만 우선 복사 후 설치 (캐시 재사용)
COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip setuptools wheel && \
    pip install --prefer-binary -r /tmp/requirements.txt

# 2) 앱 소스 복사 (+ best.pt 는 .dockerignore에서 허용됨)
COPY . /app/

# 결과 폴더 준비
RUN mkdir -p /app/results

# Render 동적 포트 사용
ENV PORT=10000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --workers 1"]