# ---- Agent0-Lite Sidecar (Phase 1) ----
# Hardened image, pinned deps, non-root, healthcheck.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=4040 \
    LOG_LEVEL=INFO \
    BUILD_VERSION=phase1-1.0.0 \
    CONFIG_PATH=/app/config.yaml

# Minimal OS deps (curl for healthcheck, ca-certs for TLS)
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    ca-certificates curl tini && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m appuser
WORKDIR /app

# Copy app
COPY app.py /app/app.py

# Install exact Python deps (no external requirements.txt needed)
RUN pip install --no-cache-dir \
    fastapi==0.115.5 \
    "uvicorn[standard]==0.32.0" \
    pyyaml==6.0.2 \
    httpx==0.27.2

# Drop privileges
USER appuser

EXPOSE 4040

# Container-level healthcheck hits the app’s /health
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fsS http://127.0.0.1:4040/health || exit 1

# Proper signal handling
ENTRYPOINT ["/usr/bin/tini","--"]

# Run the FastAPI app (file-based import avoids issues with hyphens in repo name)
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","4040"]
