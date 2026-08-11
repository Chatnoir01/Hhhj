import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';
import { calculateInvoiceTotals, validateInvoiceDraft } from './src/domain/invoice.js';

const root = fileURLToPath(new URL('.', import.meta.url));
const port = Number(process.env.PORT || 3000);

const mime = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8'
};

function sendJson(res, status, payload) {
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
  res.end(JSON.stringify(payload));
}

async function readJson(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 64_000) throw new Error('PAYLOAD_TOO_LARGE');
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
}

async function serveStatic(req, res) {
  const requested = req.url === '/' ? '/index.html' : req.url.split('?')[0];
  const safe = normalize(requested).replace(/^(\.\.(\/|\\|$))+/, '');
  const target = join(root, safe);
  if (!target.startsWith(root)) return sendJson(res, 403, { error: 'forbidden' });
  try {
    const body = await readFile(target);
    res.writeHead(200, {
      'content-type': mime[extname(target)] || 'application/octet-stream',
      'x-content-type-options': 'nosniff',
      'referrer-policy': 'no-referrer',
      'content-security-policy': "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'"
    });
    res.end(body);
  } catch {
    sendJson(res, 404, { error: 'not_found' });
  }
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === 'GET' && req.url === '/api/health') {
      return sendJson(res, 200, { ok: true, service: 'pilot', version: '0.1.0' });
    }

    if (req.method === 'POST' && req.url === '/api/invoices/preview') {
      const draft = await readJson(req);
      const errors = validateInvoiceDraft(draft);
      if (errors.length) return sendJson(res, 400, { error: 'invalid_invoice', fields: errors });
      return sendJson(res, 200, calculateInvoiceTotals(draft));
    }

    if (!['GET', 'HEAD'].includes(req.method)) {
      return sendJson(res, 405, { error: 'method_not_allowed' });
    }

    return serveStatic(req, res);
  } catch (error) {
    if (error.message === 'PAYLOAD_TOO_LARGE') return sendJson(res, 413, { error: 'payload_too_large' });
    if (error instanceof SyntaxError) return sendJson(res, 400, { error: 'invalid_json' });
    console.error(error);
    return sendJson(res, 500, { error: 'internal_error' });
  }
});

server.listen(port, () => {
  console.log(`Pilot running on http://localhost:${port}`);
});
