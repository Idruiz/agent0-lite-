# Phase 1: VS Bias → Lite Pipeline (Complete)

## Overview

This repo contains the **Agent0-Lite** service, a FastAPI-based sidecar that powers
the VS Bias Audit Builder. Phase 1 delivers a fully working end-to-end pipeline:

Client → VS Bias Proxy (Node, port 3100) → Agent0-Lite (FastAPI, port 4040) → Polish → Response

## Architecture

- **Agent0-Lite (this repo)**
  - Framework: FastAPI + Uvicorn
  - Port: `4040`
  - Endpoints:
    - `GET /health` — health check
    - `POST /polish` — VS bias prompt polish endpoint

- **VS Bias Minimal Proxy (Node)**
  - File: `~/minimal-proxy.js`
  - Port: `3100`
  - Endpoints:
    - `GET /health` — proxy health
    - `POST /api/vs-bias/polish` — forwards to Lite `/polish`

- **Contract (Pydantic)**
  - File: `contracts/vs_bias_prompt.py`
  - Model: `VSBiasPromptContract`
  - Validates:
    - `artifact_type` (currently `"vs_bias_prompt"`)
    - `content` block (user query, engineered prompt, dimensions, notes)
    - `context` block (app metadata, constraints)
    - `polish_instructions` block (goals, allowed changes, flags)
    - `request_id`

## Key Files

- `contracts/vs_bias_prompt.py`
  - Pydantic schema for the VS Bias prompt.
  - Provides `validate_vs_bias_prompt(payload: dict) -> VSBiasPromptContract`.

- `polish/vs_bias.py`
  - Core polish logic for VS Bias prompts.
  - Consumes `VSBiasPromptContract` and returns:
    - `polished_artifact` (updated engineered prompt + notes)
    - `polish_report` (summary + details)

- `app.py`
  - FastAPI application wiring:
    - `GET /health` — simple JSON health response.
    - `POST /polish` — validates payload using the contract, calls polish logic,
      and returns the result.
  - Emits JSON logs with trace-like fields for easier debugging.

- `config.yaml` (if present)
  - Optional configuration (logging, environment settings, etc.).

- **Outside this repo (but part of Phase 1):**
  - `~/minimal-proxy.js` — zero-dependency Node HTTP proxy that:
    - Listens on port `3100`.
    - Forwards `/api/vs-bias/polish` to `http://127.0.0.1:4040/polish`.
    - Provides its own `/health`.

## How to Run

### 1. Start Agent0-Lite (FastAPI service on port 4040)

```bash
cd ~/code/agent0-lite-
source .venv/bin/activate
uvicorn app:app --host 0.0.0.0 --port 4040

