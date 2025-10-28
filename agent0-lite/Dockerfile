# ---- Agent0-Lite Phase 1 Sidecar ----
# Hardened, reproducible image with healthcheck and non-root user.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=4040 \
    LOG_LEVEL=INFO \
    BUILD_VERSION=phase1-1.0.0

# System deps
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    ca-certificates curl tini && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m appuser
WORKDIR /app

# Copy repo
COPY . /app

# If you created app.py under a subfolder named "agent0-lite/",
# we set WORKDIR there so uvicorn can import "app:app" cleanly.
# (Hyphens are not valid Python module names; this avoids import errors.)
# If your app.py is at repo root, comment the next line.
WORKDIR /app/agent0-lite

# Python deps (explicit to avoid missing requirements.txt)
RUN pip install --no-cache-dir \
    fastapi==0.115.5 \
    "uvicorn[standard]==0.32.0" \
    pyyaml==6.0.2 \
    httpx==0.27.2

# Drop privileges
USER appuser

EXPOSE 4040
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD \
  curl -fsS http://127.0.0.1:4040/health || exit 1

# Tini for clean SIGTERM handling
ENTRYPOINT ["/usr/bin/tini","--"]

# Run the FastAPI app (we're already in the directory that contains app.py)
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","4040"]
