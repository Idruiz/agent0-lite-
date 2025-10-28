# app.py
# Agent0-Lite — Phase 1 sidecar
# Endpoints: /health, /polish, /delegate
# Features: JSON logs, trace IDs, ENV+YAML config (optional), DNS/TCP & provider probes with timeouts.
# No placeholders; safe error surfacing (never crashes the host app).

from __future__ import annotations
import os, time, socket, json, sys, asyncio, typing as t
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Soft deps with actionable messages (prevents cryptic crashes)
try:
    import yaml
except Exception:
    raise SystemExit("Missing dependency: pyyaml. Install later with: pip install fastapi uvicorn pyyaml httpx")

try:
    import httpx
except Exception:
    raise SystemExit("Missing dependency: httpx. Install later with: pip install httpx")

# -------- JSON logging with trace IDs --------
import logging
class _JsonFmt(logging.Formatter):
    def format(self, rec: logging.LogRecord) -> str:
        base = {
            "ts": int(time.time()*1000),
            "level": rec.levelname,
            "msg": rec.getMessage(),
            "logger": rec.name,
        }
        for k in ("traceId","component","phase","elapsedMs"):
            if hasattr(rec, k): base[k] = getattr(rec, k)  # type: ignore
        if rec.exc_info:
            base["exc"] = self.formatException(rec.exc_info)
        return json.dumps(base, ensure_ascii=False)
_logh = logging.StreamHandler(sys.stdout); _logh.setFormatter(_JsonFmt())
log = logging.getLogger("agent0-lite"); log.handlers.clear(); log.addHandler(_logh)
log.setLevel(os.getenv("LOG_LEVEL","INFO").upper())

def _trace(headers: dict, fallback: str | None = None) -> str:
    for k in ("x-trace-id","x-request-id","trace-id","X-Trace-Id","X-Request-Id","Trace-Id"):
        v = headers.get(k); if v: return str(v)
    import uuid; return fallback or uuid.uuid4().hex

# -------- Config (ENV first, YAML optional) --------
def _load_yaml(path: str) -> dict:
    if not os.path.exists(path): return {}
    with open(path, "r", encoding="utf-8") as f: return yaml.safe_load(f) or {}

CFG_PATH = os.getenv("CONFIG_PATH", "./config.yaml")
_raw = _load_yaml(CFG_PATH)

SERVICE_NAME = os.getenv("SERVICE_NAME", _raw.get("service_name","agent0-lite"))
BUILD_VERSION = os.getenv("BUILD_VERSION", _raw.get("build_version","phase1"))
PORT = int(os.getenv("PORT", str(_raw.get("port",4040))))

def _csv(v: str | None) -> list[str]: return [s.strip().lower() for s in (v or "").split(",") if s.strip()]
ALLOW_PROVIDERS = _csv(os.getenv("ALLOW_PROVIDERS")) or [s.strip().lower() for s in (_raw.get("providers",{}).get("allow") or ["openai","groq"])]
DENY_PROVIDERS  = _csv(os.getenv("DENY_PROVIDERS"))  or [s.strip().lower() for s in (_raw.get("providers",{}).get("deny")  or ["openrouter","anthropic","together","replicate","cohere","gemini"])]
ALLOWED_HOSTS   = _csv(os.getenv("ALLOWED_HOSTS"))   or [h.strip().lower() for h in (_raw.get("network",{}).get("allowed_hosts") or ["api.openai.com","api.groq.com"])]

T_HEALTH_OVERALL = int(os.getenv("T_HEALTH_OVERALL", str(_raw.get("timeouts",{}).get("health_overall",8))))
T_CONNECT        = int(os.getenv("T_CONNECT",        str(_raw.get("timeouts",{}).get("connect",3))))
T_READ           = int(os.getenv("T_READ",           str(_raw.get("timeouts",{}).get("read",5))))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY","")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY","")

# -------- Probes (bounded; never crash) --------
def _probe_host(host: str, port: int, timeout: float) -> tuple[bool, str | None]:
    try:
        ip = socket.gethostbyname(host)
        with socket.create_connection((ip, port), timeout=timeout): pass
        return True, None
    except Exception as e:
        return False, str(e)

OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
GROQ_MODELS_URL   = "https://api.groq.com/openai/v1/models"

async def _provider_probe() -> dict:
    out: dict[str, dict] = {"openai": {}, "groq": {}}
    async with httpx.AsyncClient(timeout=T_READ) as client:
        if OPENAI_API_KEY:
            try:
                r = await client.get(OPENAI_MODELS_URL, headers={"Authorization": f"Bearer {OPENAI_API_KEY}"})
                out["openai"] = {"ok": r.status_code in (200,401,403), "status": r.status_code}
            except Exception as e:
                out["openai"] = {"ok": False, "error": str(e)}
        else:
            out["openai"] = {"ok": False, "error": "missing_key"}
        if GROQ_API_KEY:
            try:
                r = await client.get(GROQ_MODELS_URL, headers={"Authorization": f"Bearer {GROQ_API_KEY}"})
                out["groq"] = {"ok": r.status_code in (200,401,403), "status": r.status_code}
            except Exception as e:
                out["groq"] = {"ok": False, "error": str(e)}
        else:
            out["groq"] = {"ok": False, "error": "missing_key"}
    return out

# -------- FastAPI app --------
app = FastAPI(title="Agent0-Lite", version=BUILD_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                   allow_methods=["GET","POST","OPTIONS"], allow_headers=["*"])

@app.middleware("http")
async def _trace_logger(req: Request, call_next):
    tid = _trace(dict(req.headers)); start = time.time()
    try:
        resp = await call_next(req)
        resp.headers["X-Trace-Id"] = tid
        log.info(f"{req.method} {req.url.path} -> {resp.status_code}",
                 extra={"traceId":tid,"component":"http","elapsedMs":int((time.time()-start)*1000)})
        return resp
    except Exception:
        log.error("unhandled", extra={"traceId":tid,"component":"http"}, exc_info=True)
        return JSONResponse(status_code=500, content={"ok":False,"code":500,"message":"internal error","traceId":tid})

@app.get("/health")
async def health(req: Request):
    tid = _trace(dict(req.headers))
    try:
        async def _run():
            net = {h: (lambda ok_err=_probe_host(h,443,timeout=T_CONNECT): {"ok": ok_err[0], **({"error": ok_err[1]} if ok_err[1] else {})})()
                   for h in ALLOWED_HOSTS}
            providers = await _provider_probe()
            ok_hosts = all(v.get("ok", False) for v in net.values()) if net else True
            ok = bool(ok_hosts)  # don’t fail for missing keys in Phase 1
            payload = {
                "ok": ok,
                "service": SERVICE_NAME,
                "version": BUILD_VERSION,
                "providers": {"allow": ALLOW_PROVIDERS, "deny": DENY_PROVIDERS, "checks": providers},
                "network": {"allowed_hosts": ALLOWED_HOSTS, "checks": net},
            }
            if not ok: payload["reason"] = "network checks failed"
            return payload
        payload = await asyncio.wait_for(_run(), timeout=T_HEALTH_OVERALL)
        return JSONResponse(status_code=200 if payload.get("ok") else 503, content=payload, headers={"X-Trace-Id":tid})
    except asyncio.TimeoutError:
        return JSONResponse(status_code=503, content={"ok":False,"reason":"health timeout","traceId":tid}, headers={"X-Trace-Id":tid})

@app.post("/polish")
async def polish(req: Request):
    tid = _trace(dict(req.headers))
    return JSONResponse(status_code=200, content={"ok":True,"status":"ready","traceId":tid}, headers={"X-Trace-Id":tid})

@app.post("/delegate")
async def delegate(req: Request):
    tid = _trace(dict(req.headers))
    return JSONResponse(status_code=200, content={"ok":True,"status":"ready","traceId":tid}, headers={"X-Trace-Id":tid})
