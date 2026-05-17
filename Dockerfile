# syntax=docker/dockerfile:1.6
  FROM python:3.12-slim

  ENV PYTHONDONTWRITEBYTECODE=1 \
      PYTHONUNBUFFERED=1 \
      PIP_NO_CACHE_DIR=1 \
      PIP_DISABLE_PIP_VERSION_CHECK=1

  WORKDIR /app

  # 의존성 캐시 효율을 위해 requirements 먼저.
  COPY requirements.txt ./
  RUN pip install -r requirements.txt

  # 앱 소스만 복사 (.dockerignore 가 tests/docs/.env 등 차단).
  COPY app ./app

  # 비-루트 사용자.
  RUN useradd --create-home --uid 10001 appuser \
      && chown -R appuser:appuser /app
  USER appuser

  EXPOSE 8000

  HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
      CMD python -c "import urllib.request,sys; \
  sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/', timeout=3).status==200 else 1)"

  # F-07 인-프로세스 WS 브로드캐스터가 single-process 가정 → workers 1.
  CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]