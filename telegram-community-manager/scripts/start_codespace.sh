#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p data logs

# Do not trust a stale process match: the web app is considered alive only if
# its health endpoint answers successfully.
if ! curl -fsS --max-time 2 http://127.0.0.1:8000/health >/dev/null 2>&1; then
  pkill -f "uvicorn app.main:app" >/dev/null 2>&1 || true
  nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000     > logs/codespace-web.log 2>&1 &

  # Wait until FastAPI is actually ready before exposing the port.
  for _ in {1..30}; do
    if curl -fsS --max-time 2 http://127.0.0.1:8000/health >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

# Re-assert public visibility on every Codespace start.
if [[ -n "${CODESPACE_NAME:-}" ]] && command -v gh >/dev/null 2>&1; then
  gh codespace ports visibility 8000:public -c "$CODESPACE_NAME"     >> logs/codespace-publish.log 2>&1 || true
fi
