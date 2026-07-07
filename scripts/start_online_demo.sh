#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cleanup() {
  if [ -n "${BACKEND_PID:-}" ]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  if [ -n "${CONNECTOR_PID:-}" ]; then kill "$CONNECTOR_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

echo "[WAACT] Starting backend on public Codespaces port 8000..."
bash "$ROOT_DIR/scripts/start_backend.sh" &
BACKEND_PID=$!

sleep 3

echo "[WAACT] Starting WhatsApp connector on private port 3001..."
bash "$ROOT_DIR/scripts/start_connector.sh" &
CONNECTOR_PID=$!

echo "[WAACT] Online demo processes are running. Keep this terminal open."
wait -n "$BACKEND_PID" "$CONNECTOR_PID"
