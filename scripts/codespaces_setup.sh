#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[WAACT] Installing Chromium runtime dependencies..."
sudo apt-get update
sudo apt-get install -y \
  libnss3 \
  libatk1.0-0 \
  libatk-bridge2.0-0 \
  libcups2 \
  libdrm2 \
  libxkbcommon0 \
  libxcomposite1 \
  libxdamage1 \
  libxfixes3 \
  libxrandr2 \
  libgbm1 \
  libasound2 \
  libpangocairo-1.0-0 \
  libpango-1.0-0 \
  libcairo2

echo "[WAACT] Installing Python dependencies..."
python -m pip install --upgrade pip
python -m pip install -r "$ROOT_DIR/backend/requirements.txt"

echo "[WAACT] Installing WhatsApp connector dependencies..."
npm install --prefix "$ROOT_DIR/whatsapp-connector"

if [ ! -f "$ROOT_DIR/backend/.env" ]; then
  cp "$ROOT_DIR/backend/.env.codespaces.example" "$ROOT_DIR/backend/.env"
  echo "[WAACT] Created backend/.env from Codespaces example. Fill Supabase and secrets before demo."
fi

if [ ! -f "$ROOT_DIR/whatsapp-connector/.env" ]; then
  cp "$ROOT_DIR/whatsapp-connector/.env.codespaces.example" "$ROOT_DIR/whatsapp-connector/.env"
  echo "[WAACT] Created whatsapp-connector/.env from Codespaces example. Match secrets with backend/.env."
fi

echo "[WAACT] Setup complete. Run: bash scripts/start_online_demo.sh"
