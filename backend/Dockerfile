# syntax=docker/dockerfile:1
FROM python:3.12.14-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY requirements.txt .
RUN python -m pip wheel --wheel-dir /wheels -r requirements.txt

FROM python:3.12.14-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"

RUN groupadd --system --gid 10001 flowpilot \
    && useradd --system --uid 10001 --gid flowpilot --home-dir /nonexistent --shell /usr/sbin/nologin flowpilot \
    && python -m venv /opt/venv \
    && mkdir -p /app /data \
    && chown -R flowpilot:flowpilot /app /data

COPY --from=builder /wheels /wheels
COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-index --find-links=/wheels -r /tmp/requirements.txt \
    && rm -rf /wheels /tmp/requirements.txt

WORKDIR /app
COPY --chown=flowpilot:flowpilot app ./app
COPY --chown=flowpilot:flowpilot migrations ./migrations
COPY --chown=flowpilot:flowpilot alembic.ini docker-entrypoint.sh ./
RUN chmod 0555 /app/docker-entrypoint.sh

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

ENTRYPOINT ["/app/docker-entrypoint.sh"]
