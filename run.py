#!/usr/bin/env python3
"""ImageMaestro Standalone Launcher
Starts the ImageMaestro server without any Pinokio dependency.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
APP_DIR = ROOT_DIR / "app"
VENV_DIR = ROOT_DIR / "venv"


def find_venv_python() -> str:
    """Find the Python executable inside the virtualenv, or fallback to current."""
    bin_dir = "bin" if sys.platform != "win32" else "Scripts"
    py_name = "python" if sys.platform != "win32" else "python.exe"

    candidate = VENV_DIR / bin_dir / py_name
    if candidate.is_file():
        return str(candidate)

    # If running inside a virtual environment already
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        return sys.executable

    return sys.executable


def find_free_port(host: str, preferred: int, span: int = 20) -> int:
    """Find a bindable port starting from preferred."""
    probe_host = "127.0.0.1" if host == "0.0.0.0" else host
    for candidate in [preferred] + [preferred + i for i in range(1, span + 1)]:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((probe_host, candidate))
            return candidate
        except OSError:
            continue
        finally:
            s.close()
    return preferred


def open_browser_when_ready(url: str, timeout: float = 30.0):
    """Wait for the web server to respond, then open browser."""
    start_time = time.time()
    import urllib.request
    while time.time() - start_time < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    time.sleep(0.5)
                    webbrowser.open(url)
                    return
        except Exception:
            pass
        time.sleep(0.5)


def main():
    if "--cloud" in sys.argv:
        forwarded = [a for a in sys.argv[1:] if a != "--cloud"]
        os.execv(sys.executable, [sys.executable, str(ROOT_DIR / "cloud_launcher.py"), *forwarded])
    parser = argparse.ArgumentParser(description="ImageMaestro Standalone Runner")
    parser.add_argument("--port", type=int, default=7860, help="Port to bind (default: 7860)")
    parser.add_argument("--host", default="127.0.0.1", help="Host address to bind (default: 127.0.0.1)")
    parser.add_argument("--listen", action="store_true", help="Bind to 0.0.0.0 for local network access")
    parser.add_argument("--gpu", default="", help="Force GPU device (e.g. mps, cuda, cuda:0, cpu)")
    parser.add_argument("--browser", action="store_true", default=True, help="Automatically open browser (default: True)")
    parser.add_argument("--no-browser", action="store_false", dest="browser", help="Do not open browser")
    parser.add_argument("--compile", action="store_true", help="Enable PyTorch compilation")
    parser.add_argument("--profile", default="-1", help="VRAM profile number")
    parser.add_argument("--verbose", default="1", help="Verbosity level")
    parser.add_argument("extra_args", nargs=argparse.REMAINDER, help="Additional arguments forwarded to backend")
    args = parser.parse_args()

    py_bin = find_venv_python()
    bind_host = "0.0.0.0" if args.listen else args.host
    if not 1 <= args.port <= 65515:
        parser.error("--port must be between 1 and 65515")
    if bind_host not in {"localhost", "127.0.0.1"}:
        print("WARNING: This API has no authentication. All reachable clients can control ImageMaestro.", flush=True)
    actual_port = find_free_port(bind_host, args.port)

    display_host = "127.0.0.1" if bind_host == "0.0.0.0" else bind_host
    ui_url = f"http://{display_host}:{actual_port}/"

    print("=" * 60)
    print("               ImageMaestro Launching...")
    print(f"  • Python Interpreter: {py_bin}")
    print(f"  • Server URL:         {ui_url}")
    print(f"  • Classic Gradio UI:  {ui_url}classic/")
    print(f"  • REST API Docs:      {ui_url}docs")
    if args.gpu:
        print(f"  • Target Device:      {args.gpu}")
    print("=" * 60 + "\n")

    env = os.environ.copy()
    env["SERVER_NAME"] = bind_host
    env["SERVER_PORT"] = str(actual_port)
    env["PYTHONUNBUFFERED"] = "1"

    # Forward arguments
    cmd = [py_bin, "launch.py"]
    if args.gpu:
        cmd.extend(["--gpu", args.gpu])
    if args.compile:
        cmd.append("--compile")
    if args.profile != "-1":
        cmd.extend(["--profile", str(args.profile)])
    if args.verbose != "1":
        cmd.extend(["--verbose", str(args.verbose)])
    if args.extra_args:
        cmd.extend(args.extra_args)

    if args.browser:
        threading.Thread(target=open_browser_when_ready, args=(ui_url,), daemon=True).start()

    try:
        proc = subprocess.run(cmd, cwd=str(APP_DIR), env=env)
        sys.exit(proc.returncode)
    except KeyboardInterrupt:
        print("\n[Maestro] Stopping server...")
        sys.exit(0)


if __name__ == "__main__":
    main()
