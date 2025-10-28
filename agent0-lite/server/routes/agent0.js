// server/routes/agent0.js
// Production proxy to Agent0-Lite sidecar.
// Uses native fetch (Node 18+). Propagates X-Trace-Id. Bounded timeouts. Clean JSON errors.

const express = require('express');
const router = express.Router();

const SIDE = process.env.AGENT0_URL || 'http://agent0-lite:4040';
const JSON_HDRS = { 'content-type': 'application/json' };

// Small helper: timeout wrapper around fetch (no extra deps)
async function timedFetch(url, opts = {}, ms = 8000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort('timeout'), ms);
  try {
    const res = await fetch(url, { ...opts, signal: ctrl.signal });
    return res;
  } finally {
    clearTimeout(t);
  }
}

// Trace-ID: reuse incoming or mint a new one
function traceId(req) {
  return (
    req.get('X-Trace-Id') ||
    req.get('x-trace-id') ||
    require('crypto').randomBytes(12).toString('hex')
  );
}

// Normalize non-JSON responses into a safe JSON error
async function safeJson(res) {
  try {
    return await res.json();
  } catch {
    const text = await res.text().catch(() => '');
    return { ok: false, error: 'sidecar returned non-JSON', text };
  }
}

router.get('/health', async (req, res) => {
  const tid = traceId(req);
  try {
    const r = await timedFetch(`${SIDE}/health`, { headers: { ...JSON_HDRS, 'X-Trace-Id': tid } }, 8000);
    const body = await safeJson(r);
    res.set('X-Trace-Id', tid).status(r.ok ? 200 : 503).json(body);
  } catch (e) {
    res.set('X-Trace-Id', tid).status(504).json({
      ok: false, code: 504, message: String(e || 'timeout'),
      traceId: tid, hints: ['sidecar unreachable', `AGENT0_URL=${SIDE}`]
    });
  }
});

router.post('/polish', express.json({ limit: '5mb' }), async (req, res) => {
  const tid = traceId(req);
  try {
    const r = await timedFetch(
      `${SIDE}/polish`,
      { method: 'POST', headers: { ...JSON_HDRS, 'X-Trace-Id': tid }, body: JSON.stringify(req.body || {}) },
      30000
    );
    const body = await safeJson(r);
    res.set('X-Trace-Id', tid).status(r.ok ? 200 : 502).json(body);
  } catch (e) {
    res.set('X-Trace-Id', tid).status(504).json({
      ok: false, code: 504, message: String(e || 'timeout'),
      traceId: tid, hints: ['sidecar polish endpoint unreachable']
    });
  }
});

router.post('/delegate', express.json({ limit: '10mb' }), async (req, res) => {
  const tid = traceId(req);
  try {
    const r = await timedFetch(
      `${SIDE}/delegate`,
      { method: 'POST', headers: { ...JSON_HDRS, 'X-Trace-Id': tid }, body: JSON.stringify(req.body || {}) },
      90000
    );
    const body = await safeJson(r);
    res.set('X-Trace-Id', tid).status(r.ok ? 200 : 502).json(body);
  } catch (e) {
    res.set('X-Trace-Id', tid).status(504).json({
      ok: false, code: 504, message: String(e || 'timeout'),
      traceId: tid, hints: ['sidecar delegate endpoint unreachable']
    });
  }
});

module.exports = router;
