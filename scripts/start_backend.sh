#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/backend"

exec python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
