# ---- 1) 가벼운 베이스 이미지 (CPU) ----
FROM python:3.10-slim

# 시스템 패키지: OpenCV/FFmpeg/글꼴 등
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    curl \
    ca-certificates \
    fonts-nanum \
 && rm -rf /var/lib/apt/lists/*

# 환경설정
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    UVICORN_WORKERS=1

# ---- 2) 작업 디렉토리 ----
WORKDIR /app

# ---- 3) requirements만 먼저 복사 → 의존성 설치 레이어 캐시 ----
# backend 폴더에 requirements.txt가 있다고 가정
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /app/requirements.txt

# ---- 4) 애플리케이션 복사 ----
# 모델 파일(best.pt) 포함해서 복사
COPY . /app

# 결과 디렉토리 미리 생성
RUN mkdir -p /app/results

# Render가 PORT 환경변수로 포트를 내려줌
ENV PORT=10000

# ---- 5) 실행 커맨드 ----
# main.py에 FastAPI `app`이 있다고 가정
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}
