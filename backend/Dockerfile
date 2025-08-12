FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libgl1 libglib2.0-0 ca-certificates fonts-nanum \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

# requirements 레이어 캐시
COPY backend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip setuptools wheel && \
    pip install --prefer-binary -r requirements.txt

# 앱 코드 복사 (모델 포함)
COPY backend/ ./
RUN mkdir -p /app/results

ENV PORT=10000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
