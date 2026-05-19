# syntax=docker/dockerfile:1.7
# Multi-stage build: deps compiled in builder, runtime image stays slim.

FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# grpcio + cryptography wheels need a compiler on some arches; install only in builder.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip install --user -r requirements.txt


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/app/.local/bin:$PATH \
    API_HOST=0.0.0.0 \
    API_PORT=8080

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder --chown=app:app /root/.local /home/app/.local
COPY --chown=app:app src/ ./src/
COPY --chown=app:app main.py ./

USER app
EXPOSE 8080

# Liveness probe inside the container; orchestrators should hit /ready externally.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health', timeout=3).status == 200 else 1)" \
    || exit 1

# Single worker per container; horizontal scaling is the orchestrator's job
# (Cloud Run / k8s replicas). Multi-worker breaks per-process semaphores.
CMD ["python", "-m", "uvicorn", "src.api:app", \
     "--host", "0.0.0.0", "--port", "8080", \
     "--workers", "1", \
     "--timeout-graceful-shutdown", "90"]
