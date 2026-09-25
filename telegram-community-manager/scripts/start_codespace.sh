#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p data logs

if ! pgrep -f "uvicorn app.main:app" >/dev/null 2>&1; then
  nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > logs/codespace-web.log 2>&1 &
fi

# After the first admin setup, re-assert public visibility on each Codespace start.
# GitHub resets public forwarded ports to private on restart, so this keeps the
# panel reachable without another manual Ports-panel action.
if [[ -f data/runtime_config.json && -n "${CODESPACE_NAME:-}" ]] && command -v gh >/dev/null 2>&1; then
  (
    sleep 5
    gh codespace ports visibility 8000:public -c "$CODESPACE_NAME"       >> logs/codespace-publish.log 2>&1 || true
  ) &
fi
