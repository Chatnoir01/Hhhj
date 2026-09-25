#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p data logs

if pgrep -f "uvicorn app.main:app" >/dev/null 2>&1; then
  exit 0
fi

nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > logs/codespace-web.log 2>&1 &
