# app.py
# Agent0-Lite Phase 1 — self-contained sidecar (no other project files required)
# Endpoints: /health, /polish, /delegate
# Features: ENV+YAML config, provider allow/deny, host allowlist, DNS/TCP probes, provider probes, JSON logs, trace IDs

from __future__ import annotations
import os, time, socket, json, sys, asyncio, typing as t

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

try:
    import yaml
except Exception:
    raise SystemExit("Missing dependency: pyyaml. Install with: pip install fastapi uvicorn pyyaml httpx")

try:
    import httpx
except Exception:
    raise SystemExit("Missing dependency: httpx. Install with: pip install httpx")

# ----------------------------
# Logging (JSON w/ trace IDs)
# ----------------------------
import logging
class _JsonFmt(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": int(time.time()*1000),
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
        }
        for k in ("traceId","component","phase","status","elapsedMs"):
            if hasattr(record, k):
                base[k] = getattr(record, k)  # type: ignore
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base, ensure_ascii=False)

_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_JsonFmt())
log = logging.getLogger("agent0-lite")
log.handlers.clear()
log.addHandler(_handler)
log.setLevel(os.getenv("LOG_LEVEL","INFO").upper())

def _trace(headers: dict, fallback: str | None = None) -> str:
    for k in ("x-trace-id","x-request-id","trace-id","X-Trace-Id","X-Request-Id","Trace-Id"):
        v = headers.get(k)
        if v: return str(v)
    import uuid
    return fallback or uuid.uuid4().hex

# ----------------------------
# Config loader (ENV + YAML)
# ----------------------------
def _load_yaml(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _split_csv(v: str | None) -> list[str]:
    return [s.strip().lower() for s in (v or "").split(",") if s.strip()]

CFG_PATH = os.getenv("CONFIG_PATH", "./config.yaml")
_raw = _load_yaml(CFG_PATH)

SERVICE_NAME = os.getenv("SERVICE_NAME",       _raw.get("service_name","agent0-lite"))
BUILD_VERSION = os.getenv("BUILD_VERSION",     _raw.get("build_version","phase1"))
PORT = int(os.getenv("PORT", str(_raw.get("port",4040))))

ALLOW_PROVIDERS = _split_csv(os.getenv("ALLOW_PROVIDERS")) or [s.strip().lower() for s in (_raw.get("providers",{}).get("allow") or ["openai","groq"])]
DENY_PROVIDERS  = _split_csv(os.getenv("DENY_PROVIDERS"))  or [s.strip().lower() for s in (_raw.get("providers",{}).get("deny")  or ["openrouter","anthropic","together","replicate","cohere","gemini"])]

ALLOWED_HOSTS = _split_csv(os.getenv("ALLOWED_HOSTS")) or [h.strip().lower() for h in (_raw.get("network",{}).get("allowed_hosts") or ["api.openai.com","api.groq.com"])]

T_HEALTH_OVERALL = int(os.getenv("T_HEALTH_OVERALL", str(_raw.get("timeouts",{}).get("health_overall",8))))
T_DNS            = int(os.getenv("T_DNS",            str(_raw.get("timeouts",{}).get("dns",2))))
T_CONNECT        = int(os.getenv("T_CONNECT",        str(_raw.get("timeouts",{}).get("connect",3))))
T_READ           = int(os.getenv("T_READ",           str(_raw.get("timeouts",{}).get("read",5))))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY","")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY","")

# ----------------------------
# Probes (DNS/TCP + Providers)
# ----------------------------
def _probe_host(host: str, port: int, timeout: float) -> tuple[bool, str | None]:
    try:
        ip = socket.gethostbyname(host)
        with socket.create_connection((ip, port), timeout=timeout):
            pass
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

# ----------------------------
# FastAPI app
# ----------------------------
app = FastAPI(title="Agent0-Lite", version=BUILD_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=False,
    allow_methods=["GET","POST","OPTIONS"], allow_headers=["*"]
)

@app.middleware("http")
async def _trace_logger(req: Request, call_next):
    tid = _trace(dict(req.headers))
    start = time.time()
    try:
        res = await call_next(req)
        elapsed = int((time.time()-start)*1000)
        log.info(f"{req.method} {req.url.path} -> {res.status_code}",
                 extra={"traceId":tid,"component":"http","elapsedMs":elapsed})
        res.headers["X-Trace-Id"] = tid
        return res
    except Exception:
        elapsed = int((time.time()-start)*1000)
        log.error("unhandled", extra={"traceId":tid,"component":"http","elapsedMs":elapsed}, exc_info=True)
        return JSONResponse(status_code=500, content={"ok":False,"code":500,"message":"internal error","traceId":tid})

@app.get("/health")
async def health(req: Request):
    tid = _trace(dict(req.headers))
    try:
        async def _do():
            result: dict[str,t.Any] = {
                "service": SERVICE_NAME,
                "version": BUILD_VERSION,
                "providers": {"allow": ALLOW_PROVIDERS, "deny": DENY_PROVIDERS},
                "network": {"allowed_hosts": ALLOWED_HOSTS},
                "checks": {}
            }
            # DNS/TCP to allowed hosts
            net = {}
            for host in ALLOWED_HOSTS:
                ok, err = _probe_host(host, 443, timeout=T_CONNECT)
                net[host] = {"ok": ok, **({"error": err} if err else {})}
            result["checks"]["network"] = net

            # Provider HTTP probe (soft-fail if no keys provided)
            result["checks"]["providers"] = await _provider_probe()

            ok_hosts = all(v.get("ok", False) for v in net.values()) if net else True
            ok_providers = True  # don’t hard-fail Phase 1 if keys missing
            result["ok"] = bool(ok_hosts and ok_providers)
            if not result["ok"]:
                result["reason"] = "network checks failed"
            return result

        payload = await asyncio.wait_for(_do(), timeout=T_HEALTH_OVERALL)
        status = 200 if payload.get("ok") else 503
        return JSONResponse(status_code=status, content=payload, headers={"X-Trace-Id":tid})
    except asyncio.TimeoutError:
        return JSONResponse(status_code=503, content={"ok":False,"reason":"health timeout","traceId":tid}, headers={"X-Trace-Id":tid})

@app.post("/polish")
async def polish(req: Request):
    # Phase 1: endpoint exists and returns ready (logic arrives Phase 2)
    tid = _trace(dict(req.headers))
    return JSONResponse(status_code=200, content={"ok":True,"status":"ready","traceId":tid}, headers={"X-Trace-Id":tid})

@app.post("/delegate")
async def delegate(req: Request):
    # Phase 1: endpoint exists and returns ready (logic arrives Phase 2)
    tid = _trace(dict(req.headers))
    return JSONResponse(status_code=200, content={"ok":True,"status":"ready","traceId":tid}, headers={"X-Trace-Id":tid})


# Dev runner: uvicorn app:app --host 0.0.0.0 --port 4040
