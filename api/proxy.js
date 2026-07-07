function getBackendBaseUrl() {
  const value = process.env.CODESPACE_BACKEND_URL || process.env.BACKEND_URL || '';
  return value.replace(/\/+$/, '');
}

function getPath(req) {
  const value = req.query && req.query.path;
  if (Array.isArray(value)) return value.join('/');
  return value || '';
}

async function readBody(req) {
  if (req.method === 'GET' || req.method === 'HEAD') return undefined;
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return Buffer.concat(chunks);
}

function copyRequestHeaders(req) {
  const headers = { ...req.headers };
  delete headers.host;
  delete headers.connection;
  delete headers['content-length'];
  delete headers['accept-encoding'];
  return headers;
}

function sendSetupPage(res) {
  res.statusCode = 503;
  res.setHeader('content-type', 'text/html; charset=utf-8');
  res.end(`<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WAACT Demo Setup</title><body style="font-family:Segoe UI,Tahoma,Arial;background:#0f0f1a;color:#fff;display:grid;place-items:center;min-height:100vh;margin:0"><main style="max-width:720px;background:#1a1a2e;border:1px solid #2a2a4a;border-radius:18px;padding:28px"><h1 style="color:#00d4aa;margin-top:0">WAACT Online Demo</h1><p>ضع رابط Codespaces العام في Vercel Environment Variable باسم <code>CODESPACE_BACKEND_URL</code>.</p><p>مثال: <code>https://YOUR-CODESPACE-8000.app.github.dev</code></p></main></body></html>`);
}

module.exports = async function proxy(req, res) {
  const backendBaseUrl = getBackendBaseUrl();
  if (!backendBaseUrl) {
    sendSetupPage(res);
    return;
  }

  const path = getPath(req).replace(/^\/+/, '');
  const url = new URL(`${backendBaseUrl}/${path}`);
  for (const [key, value] of Object.entries(req.query || {})) {
    if (key === 'path') continue;
    if (Array.isArray(value)) {
      for (const item of value) url.searchParams.append(key, item);
    } else if (value !== undefined) {
      url.searchParams.set(key, value);
    }
  }

  try {
    const upstream = await fetch(url, {
      method: req.method,
      headers: copyRequestHeaders(req),
      body: await readBody(req),
      redirect: 'manual',
    });

    res.statusCode = upstream.status;
    const skipHeaders = new Set(['connection', 'content-encoding', 'transfer-encoding']);
    upstream.headers.forEach((value, key) => {
      if (!skipHeaders.has(key.toLowerCase()) && key.toLowerCase() !== 'set-cookie') {
        res.setHeader(key, value);
      }
    });
    if (typeof upstream.headers.getSetCookie === 'function') {
      const cookies = upstream.headers.getSetCookie();
      if (cookies.length) res.setHeader('set-cookie', cookies);
    } else {
      const cookie = upstream.headers.get('set-cookie');
      if (cookie) res.setHeader('set-cookie', cookie);
    }

    const buffer = Buffer.from(await upstream.arrayBuffer());
    res.end(buffer);
  } catch (error) {
    res.statusCode = 502;
    res.setHeader('content-type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ success: false, error: error.message }));
  }
};
