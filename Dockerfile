# Phase 4 — Railway 배포용 이미지.
# 웹(app.main:app), 렌더워커(app.media.worker), 게시상태워커(app.upload.queue_worker) 세
# 프로세스가 이 이미지를 공유한다 (Railway에서 서비스별로 시작 커맨드만 다르게 지정).

FROM python:3.11-slim

# ffmpeg: Phase 3 미디어 조립 / fonts-nanum: 한글 자막·썸네일 번인(SIL OFL, 라이선스 문제 없음)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p renders assets/bgm assets/fonts

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# 기본 CMD는 웹 프로세스. Railway에서 렌더워커/게시상태워커 서비스는
# start command를 각각 "python -m app.media.worker", "python -m app.upload.queue_worker"로 덮어쓴다.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
