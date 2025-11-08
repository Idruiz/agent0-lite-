# Agent0-Lite – Phase 1 sidecar
# Endpoints: /health, /polish, /delegate
# Features: JSON logs, trace IDs, optional YAML config.
# No placeholders on HTTP surface; errors are surfaced as JSON, never crash the host.

from __future__ import annotations

import json
import logging
import os
import socket
import time
from typing import Any, Dict

import yaml  # expected to be installed with the image
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from contracts.vs_bias_prompt import validate_vs_bias_prompt
from polish.vs_bias import polish_vs_bias_prompt


# -------- JSON logging with trace IDs --------


class JsonFmt(logging.Formatter):
    def format(self, rec: logging.LogRecord) -> str:
        base: Dict[str, Any] = {
            "ts": int(time.time() * 1000),
            "level": rec.levelname,
            "msg": rec.getMessage(),
            "logger": rec.name,
        }
        for k in ("traceId", "component", "phase", "elapsedMs"):
            if hasattr(rec, k):
                base[k] = getattr(rec, k)
        if rec.exc_info:
            base["exc"] = self.formatException(rec.exc_info)
        return json.dumps(base, ensure_ascii=False)


_handler = logging.StreamHandler()
_handler.setFormatter(JsonFmt())
logging.basicConfig(level=logging.INFO, handlers=[_handler])
log = logging.getLogger("agent0-lite")


def _trace(headers: Dict[str, Any] | None = None) -> str:
    """Generate a simple trace ID."""
    base = int(time.time() * 1000)
    host = socket.gethostname()
    extra = ""
    if headers:
        # allow a header to pass through an upstream trace id if present
        extra = headers.get("x-trace-id", "") or headers.get("X-Trace-Id", "") or ""
    tid = f"{host}-{base}"
    if extra:
        tid = f"{tid}-{extra}"
    return tid


# -------- Config --------

CFG_PATH = os.getenv("CONFIG_PATH", "./config.yaml")

SERVICE_NAME = "agent0-lite"
BUILD_VERSION = "phase1"
PORT = 4040

try:
    if os.path.exists(CFG_PATH):
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        SERVICE_NAME = str(raw.get("service_name", SERVICE_NAME))
        BUILD_VERSION = str(raw.get("build_version", BUILD_VERSION))
        PORT = int(raw.get("port", PORT))
except Exception as e:
    log.warning("Failed to load config.yaml, using defaults", extra={"component": "config", "error": str(e)})


# -------- FastAPI app --------

app = FastAPI(title=SERVICE_NAME, version=BUILD_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
    allow_methods=["*"],
)


# -------- Health --------


@app.get("/health")
async def health() -> JSONResponse:
    """
    Simple health endpoint.

    Later this can probe providers, DNS, etc., but for Phase 1 we just
    confirm the process is alive and responding.
    """
    tid = _trace()
    log.info("health check", extra={"traceId": tid, "component": "health"})
    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "service": SERVICE_NAME,
            "version": BUILD_VERSION,
            "traceId": tid,
        },
        headers={"X-Trace-Id": tid},
    )


# -------- Polish: VS Bias Phase 1 --------


@app.post("/polish")
async def polish(req: Request) -> JSONResponse:
    """
    Phase 1 VS Bias polish endpoint.

    Expects a vs_bias_prompt contract payload and returns:
      - polished_artifact
      - polish_report
    """
    tid = _trace(dict(req.headers))

    try:
        payload = await req.json()
    except Exception:
        log.warning("polish: invalid JSON body", extra={"traceId": tid, "component": "polish"})
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    log.info(
        "polish request received",
        extra={
            "traceId": tid,
            "component": "polish",
            "artifact_type": payload.get("artifact_type"),
        },
    )

    if payload.get("artifact_type") != "vs_bias_prompt":
        raise HTTPException(
            status_code=400,
            detail="Only 'vs_bias_prompt' artifact_type is supported in Phase 1",
        )

    # Validate against the contract
    try:
        contract = validate_vs_bias_prompt(payload)
    except Exception as e:
        log.warning(
            "polish validation failed",
            extra={"traceId": tid, "component": "polish", "error": str(e)},
        )
        raise HTTPException(status_code=400, detail=f"Invalid vs_bias_prompt payload: {e}")

    # Run the actual polish logic
    result = polish_vs_bias_prompt(contract)

    log.info(
        "polish completed",
        extra={"traceId": tid, "component": "polish", "artifact_type": contract.artifact_type},
    )

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "artifact_type": contract.artifact_type,
            "polished_artifact": result["polished_artifact"],
            "polish_report": result["polish_report"],
            "traceId": tid,
        },
        headers={"X-Trace-Id": tid},
    )


# -------- Delegate stub (for future phases) --------


@app.post("/delegate")
async def delegate(req: Request) -> JSONResponse:
    """
    Phase 1 delegate stub.

    We keep the endpoint alive, but it only echoes that delegation is not yet implemented.
    """
    tid = _trace(dict(req.headers))
    log.info("delegate request received (stub)", extra={"traceId": tid, "component": "delegate"})

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "status": "delegate_not_implemented",
            "traceId": tid,
        },
        headers={"X-Trace-Id": tid},
    )
