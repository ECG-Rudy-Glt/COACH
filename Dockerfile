# syntax=docker/dockerfile:1
FROM python:3.12-slim

LABEL org.opencontainers.image.title="COACH" \
      org.opencontainers.image.description="Self-hosted adaptive sports coach: rules-based training plans, nutrition suggestions, optional LLM coach." \
      org.opencontainers.image.source="https://github.com/ECG-Rudy-Glt/COACH" \
      org.opencontainers.image.licenses="AGPL-3.0-only"

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MIGRATIONS_DIR=/srv/migrations MEDIA_DIR=/srv/media
WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app app
COPY questions questions
COPY data data
COPY db/migrations migrations

# Unprivileged user; the media directory is created here so a named volume inherits its ownership.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin coach \
    && mkdir -p /srv/media && chown coach /srv/media
USER 10001

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
