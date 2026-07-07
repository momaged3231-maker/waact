#!/usr/bin/env python3
"""
WAACT - WhatsApp Automation System
Run script for MVP
"""

import os
import sys
import subprocess
import signal
import time
import socket

BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
CONNECTOR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whatsapp-connector")


def print_banner():
    print("""
    ╔══════════════════════════════════════════╗
    ║         WAACT - WhatsApp Automation      ║
    ║         نظام أتمتة الواتساب الذكي        ║
    ╚══════════════════════════════════════════╝
    """)


def run_backend():
    if port_in_use(8000):
        print("[WAACT] Backend already appears to be running on http://localhost:8000")
        print("[WAACT] Stop the old backend before starting a new one.")
        return

    os.chdir(BACKEND_DIR)
    print("[WAACT] Starting backend server on http://localhost:8000")
    print("[WAACT] Dashboard: http://localhost:8000")
    print("[WAACT] API Health: http://localhost:8000/api/health")
    print()

    subprocess.run([
        sys.executable, "-m", "uvicorn", "main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
    ])


def dependencies_installed() -> bool:
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
        import sqlalchemy  # noqa: F401
        import chromadb  # noqa: F401
        import openai  # noqa: F401
        import tiktoken  # noqa: F401
        import apscheduler  # noqa: F401
        import httpx  # noqa: F401
        import jinja2  # noqa: F401
        import multipart  # noqa: F401
        import aiofiles  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def run_all():
    print_banner()

    if dependencies_installed():
        print("[WAACT] Dependencies already installed - skipping pip install.")
    else:
        print("[WAACT] Installing Python dependencies...")
        subprocess.run([
            sys.executable, "-m", "pip", "install", "-r",
            os.path.join(BACKEND_DIR, "requirements.txt"),
        ], check=True)

    if port_in_use(8000):
        print("[WAACT] Port 8000 is already in use. Stop the old backend first, then run again.")
        return

    print("[WAACT] Initializing database...")
    from backend.database.db import init_db
    init_db()
    print("[WAACT] Database ready.")

    print("[WAACT] Installing Node.js dependencies...")
    if os.path.exists(os.path.join(CONNECTOR_DIR, "package.json")):
        subprocess.run(["npm", "install"], cwd=CONNECTOR_DIR, capture_output=True)

    print()
    print("=" * 50)
    print("  WAACT System Starting...")
    print("  Dashboard : http://localhost:8000")
    print("  API       : http://localhost:8000/api/health")
    print("=" * 50)
    print()
    print("  IMPORTANT: Set your OPENAI_API_KEY in backend/.env")
    print("  IMPORTANT: Run WhatsApp connector separately:")
    print("    cd whatsapp-connector && npm start")
    print()

    run_backend()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="WAACT - WhatsApp Automation System")
    parser.add_argument("--mode", choices=["backend", "all"], default="backend",
                        help="Run mode: backend only or all components")

    args = parser.parse_args()

    if args.mode == "all":
        run_all()
    else:
        print_banner()
        run_backend()
